//! Local passage selection and tentative word comparison. No audio or network I/O.
use serde::{Deserialize, Serialize};
use unicode_normalization::{char::is_combining_mark, UnicodeNormalization};
use wasm_bindgen::prelude::*;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(untagged)]
pub enum VerseId {
    Number(u32),
    Label(String),
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Word {
    pub text: String,
    pub position: usize,
    pub forms: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Verse {
    pub id: VerseId,
    pub source: String,
    pub words: Vec<Word>,
}
#[derive(Deserialize)]
pub struct Record {
    pub surah: u32,
    pub ayah: u32,
    pub text_uthmani: String,
}
#[derive(Serialize, Debug, PartialEq)]
pub struct Skip {
    pub verse: VerseId,
    pub position: usize,
}
#[derive(Serialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct Feedback {
    pub status: &'static str,
    pub reason: Option<&'static str>,
    pub pronunciation: &'static str,
    pub outside_words: usize,
    pub skips: Vec<Skip>,
    pub repeats: Vec<VerseId>,
}
fn unsure(reason: &'static str) -> Feedback {
    Feedback {
        status: "unsure",
        reason: Some(reason),
        pronunciation: "unsure",
        outside_words: 0,
        skips: vec![],
        repeats: vec![],
    }
}
pub fn normalize(text: &str) -> Vec<String> {
    text.nfc()
        .filter_map(|c| {
            if is_combining_mark(c)
                || c == 'ـ'
                || matches!(c as u32, 0x610..=0x61a | 0x64b..=0x65f | 0x670 | 0x6d6..=0x6ed)
            {
                None
            } else if matches!(c, 'أ' | 'إ' | 'آ' | 'ٱ') {
                Some('ا')
            } else if c.is_alphanumeric() || c.is_whitespace() {
                Some(c)
            } else {
                Some(' ')
            }
        })
        .collect::<String>()
        .split_whitespace()
        .map(str::to_owned)
        .collect()
}
fn forms(text: &str) -> Vec<String> {
    let mut words = normalize(text);
    words.extend(normalize(&text.replace('\u{670}', "ا")));
    words.sort();
    words.dedup();
    words
}
pub fn verse_count(surah: u32) -> Option<u32> {
    match surah {
        1 => Some(7),
        112 => Some(4),
        67..=77 => Some([30, 52, 52, 44, 28, 28, 20, 56, 40, 31, 50][(surah - 67) as usize]),
        _ => None,
    }
}
pub fn select_reference(
    records: &[Record],
    surah: u32,
    basmala: bool,
) -> Result<Vec<Verse>, String> {
    let count = verse_count(surah).ok_or("Unsupported passage")?;
    let rows: Vec<_> = records.iter().filter(|r| r.surah == surah).collect();
    if rows.len() != count as usize
        || rows
            .iter()
            .enumerate()
            .any(|(i, r)| r.ayah as usize != i + 1 || r.text_uthmani.trim().is_empty())
    {
        return Err("Invalid reference".into());
    }
    let openings: Vec<_> = records
        .iter()
        .filter(|r| r.surah == 1 && r.ayah == 1)
        .collect();
    if openings.len() != 1 {
        return Err("Invalid opening".into());
    }
    let prefix = normalize(&openings[0].text_uthmani);
    let mut verses: Vec<Verse> = rows
        .into_iter()
        .map(|r| Verse {
            id: VerseId::Number(r.ayah),
            source: r.text_uthmani.clone(),
            words: r
                .text_uthmani
                .split_whitespace()
                .filter(|w| !forms(w).is_empty())
                .enumerate()
                .map(|(i, w)| Word {
                    text: w.into(),
                    position: i + 1,
                    forms: forms(w),
                })
                .collect(),
        })
        .collect();
    if surah != 1 {
        if prefix.len() != 4
            || !prefix.iter().enumerate().all(|(i, w)| {
                verses[0]
                    .words
                    .get(i)
                    .is_some_and(|word| word.forms.contains(w))
            })
        {
            return Err("Unexpected opening boundary".into());
        }
        let opening_words: Vec<_> = verses[0].words.drain(..4).collect();
        if basmala {
            verses.insert(
                0,
                Verse {
                    id: VerseId::Label("opening".into()),
                    source: openings[0].text_uthmani.clone(),
                    words: opening_words,
                },
            );
        }
    }
    if verses
        .iter()
        .any(|v| v.words.is_empty() || v.words.iter().any(|w| w.forms.is_empty()))
    {
        return Err("Empty reference".into());
    }
    Ok(verses)
}
pub fn passage(
    records: &[Record],
    surah: u32,
    first: u32,
    last: u32,
    basmala: bool,
) -> Result<Vec<Verse>, String> {
    if first == 0 || last < first || last > verse_count(surah).ok_or("Unsupported passage")? {
        return Err("Choose a valid verse range".into());
    }
    let verses: Vec<_> = select_reference(records, surah, basmala && first == 1)?
        .into_iter()
        .filter(|v| match v.id {
            VerseId::Number(n) => n >= first && n <= last,
            _ => first == 1,
        })
        .collect();
    if verses.iter().map(|v| v.words.len()).sum::<usize>() > 100 {
        return Err("Choose fewer verses (up to 100 words per attempt)".into());
    }
    Ok(verses)
}
#[derive(Serialize)]
struct Choice {
    surah: u32,
    first: u32,
    last: u32,
}
fn choose(records: &[Record], scope: &[u32], seed: u32, length: u32) -> Result<Choice, String> {
    if scope.is_empty() || scope.len() > 13 || !(1..=3).contains(&length) {
        return Err("Invalid selection".into());
    }
    let mut candidates = Vec::new();
    for &surah in scope {
        let count = verse_count(surah).ok_or("Unsupported passage")?;
        let reference = select_reference(records, surah, false)?;
        for first in 1..=count {
            let last = (first + length - 1).min(count);
            let words: usize = reference[(first - 1) as usize..last as usize]
                .iter()
                .map(|v| v.words.len())
                .sum();
            if words <= 100 {
                candidates.push(Choice { surah, first, last });
            }
        }
    }
    if candidates.is_empty() {
        return Err("No passage fits this selection".into());
    }
    Ok(candidates.swap_remove(seed as usize % candidates.len()))
}
#[derive(Clone, Copy, PartialEq)]
enum Op {
    Match,
    Skip,
    Extra,
    Different,
    Repeat,
}
#[derive(Clone, Copy)]
struct Cell {
    cost: usize,
    ways: u8,
    previous: Option<(usize, usize, Op)>,
}
fn advance(cells: &mut [Vec<Cell>], from: (usize, usize), to: (usize, usize), cost: usize, op: Op) {
    let origin = cells[from.0][from.1];
    let target = &mut cells[to.0][to.1];
    let value = origin.cost + cost;
    if value < target.cost {
        *target = Cell {
            cost: value,
            ways: origin.ways,
            previous: Some((from.0, from.1, op)),
        };
    } else if value == target.cost {
        target.ways = (target.ways + origin.ways).min(2);
    }
}
pub fn compare(verses: &[Verse], text: &str) -> Feedback {
    if text.chars().count() > 5000 {
        return unsure("invalid");
    }
    let heard = normalize(text);
    let reference: Vec<_> = verses
        .iter()
        .flat_map(|v| v.words.iter().map(move |w| (w, &v.id)))
        .collect();
    let (n, m) = (reference.len(), heard.len());
    if n == 0 || n > 100 || m == 0 || m > 200 {
        return unsure("not_enough_words");
    }
    let mut endings = vec![None; n + 1];
    let mut end = 0;
    for v in verses {
        end += v.words.len();
        endings[end] = Some(v);
    }
    let mut cells = vec![
        vec![
            Cell {
                cost: usize::MAX / 2,
                ways: 0,
                previous: None
            };
            m + 1
        ];
        n + 1
    ];
    cells[0][0].cost = 0;
    cells[0][0].ways = 1;
    for i in 0..=n {
        for j in 0..=m {
            if cells[i][j].ways == 0 {
                continue;
            }
            if i < n {
                advance(&mut cells, (i, j), (i + 1, j), 1, Op::Skip);
            }
            if i > 0 && j < m {
                advance(&mut cells, (i, j), (i, j + 1), 1, Op::Extra);
            }
            if i < n && j < m {
                let matched = reference[i].0.forms.contains(&heard[j]);
                advance(
                    &mut cells,
                    (i, j),
                    (i + 1, j + 1),
                    usize::from(!matched),
                    if matched { Op::Match } else { Op::Different },
                );
            }
            if let Some(v) = endings[i] {
                if j + v.words.len() <= m
                    && v.words
                        .iter()
                        .enumerate()
                        .all(|(k, w)| w.forms.contains(&heard[j + k]))
                {
                    advance(&mut cells, (i, j), (i, j + v.words.len()), 1, Op::Repeat);
                }
            }
        }
    }
    let candidates: Vec<_> = (m.saturating_sub(2)..=m)
        .filter(|&j| {
            heard[j..]
                .iter()
                .all(|w| reference.iter().all(|r| !r.0.forms.contains(w)))
        })
        .collect();
    let best = candidates.iter().map(|&j| cells[n][j].cost).min().unwrap();
    let ends: Vec<_> = candidates
        .into_iter()
        .filter(|&j| cells[n][j].cost == best)
        .collect();
    if ends
        .iter()
        .map(|&j| u32::from(cells[n][j].ways))
        .sum::<u32>()
        != 1
    {
        return unsure("ambiguous");
    }
    let (mut i, mut j) = (n, ends[0]);
    let mut steps = Vec::new();
    while i > 0 {
        let Some((pi, pj, op)) = cells[i][j].previous else {
            return unsure("invalid");
        };
        steps.push((op, pi));
        i = pi;
        j = pj;
    }
    steps.reverse();
    if steps.iter().filter(|s| s.0 == Op::Match).count() * 10 < n * 7
        || steps
            .iter()
            .any(|s| matches!(s.0, Op::Different | Op::Extra))
    {
        return unsure("unclear_words");
    }
    if steps.first().is_some_and(|s| s.0 == Op::Skip)
        || steps.last().is_some_and(|s| s.0 == Op::Skip)
    {
        return unsure("incomplete_passage");
    }
    Feedback {
        status: "tentative",
        reason: None,
        pronunciation: "unsure",
        outside_words: j + m - ends[0],
        skips: steps
            .iter()
            .filter(|s| s.0 == Op::Skip)
            .map(|s| Skip {
                verse: reference[s.1].1.clone(),
                position: reference[s.1].0.position,
            })
            .collect(),
        repeats: steps
            .iter()
            .filter(|s| s.0 == Op::Repeat)
            .map(|s| endings[s.1].unwrap().id.clone())
            .collect(),
    }
}
fn json<T: Serialize>(value: &T) -> String {
    serde_json::to_string(value).expect("serializable output")
}
fn records(input: &str) -> Result<Vec<Record>, JsValue> {
    if input.len() > 8_000_000 {
        return Err(JsValue::from_str("Reference too large"));
    }
    serde_json::from_str(input).map_err(|_| JsValue::from_str("Invalid reference"))
}
#[wasm_bindgen]
pub fn normalize_json(text: &str) -> String {
    json(&normalize(text))
}
#[wasm_bindgen]
pub fn select_reference_json(input: &str, surah: u32, basmala: bool) -> Result<String, JsValue> {
    select_reference(&records(input)?, surah, basmala)
        .map(|v| json(&v))
        .map_err(|e| JsValue::from_str(&e))
}
#[wasm_bindgen]
pub fn passage_json(
    input: &str,
    surah: u32,
    first: u32,
    last: u32,
    basmala: bool,
) -> Result<String, JsValue> {
    passage(&records(input)?, surah, first, last, basmala)
        .map(|v| json(&v))
        .map_err(|e| JsValue::from_str(&e))
}
#[wasm_bindgen]
pub fn choose_json(input: &str, scope: &str, seed: u32, length: u32) -> Result<String, JsValue> {
    if scope.len() > 256 {
        return Err(JsValue::from_str("Invalid selection"));
    }
    let scope: Vec<u32> =
        serde_json::from_str(scope).map_err(|_| JsValue::from_str("Invalid selection"))?;
    choose(&records(input)?, &scope, seed, length)
        .map(|v| json(&v))
        .map_err(|e| JsValue::from_str(&e))
}
#[wasm_bindgen]
pub fn compare_json(input: &str, text: &str) -> String {
    if input.len() > 250_000 {
        return json(&unsure("invalid"));
    }
    match serde_json::from_str::<Vec<Verse>>(input) {
        Ok(v) => json(&compare(&v, text)),
        Err(_) => json(&unsure("invalid")),
    }
}
