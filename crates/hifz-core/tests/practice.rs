//! Synthetic Latin fixtures exercise contracts; these are not Qur'an text.
use hifz_core::{
    compare, normalize, passage, select_reference, verse_count, Record, Verse, VerseId, Word,
};

fn records() -> Vec<Record> {
    let mut rows = vec![];
    for surah in [1, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 112] {
        for ayah in 1..=verse_count(surah).unwrap() {
            let text = if ayah == 1 && surah == 1 {
                "alpha beta gamma delta".to_owned()
            } else if ayah == 1 {
                format!("alpha beta gamma delta item{surah}a{ayah} end{surah}a{ayah}")
            } else {
                format!("item{surah}a{ayah} end{surah}a{ayah}")
            };
            rows.push(Record {
                surah,
                ayah,
                text_uthmani: text,
            });
        }
    }
    rows
}
fn verse(id: u32, text: &str) -> Verse {
    Verse {
        id: VerseId::Number(id),
        source: text.into(),
        words: text
            .split_whitespace()
            .enumerate()
            .map(|(i, text)| Word {
                text: text.into(),
                position: i + 1,
                forms: normalize(text),
            })
            .collect(),
    }
}
fn assert_unsure(verses: &[Verse], text: &str) {
    let result = compare(verses, text);
    assert_eq!(result.status, "unsure");
    assert_eq!(result.pronunciation, "unsure");
    assert!(result.skips.is_empty());
    assert!(result.repeats.is_empty());
}

#[test]
fn juz_29_counts_and_supported_scope_are_explicit() {
    let expected = [30, 52, 52, 44, 28, 28, 20, 56, 40, 31, 50];
    assert_eq!(expected.iter().sum::<u32>(), 431);
    for (i, count) in expected.into_iter().enumerate() {
        assert_eq!(verse_count(67 + i as u32), Some(count));
    }
    for unsupported in [0, 2, 66, 78, 111, 113, u32::MAX] {
        assert_eq!(verse_count(unsupported), None);
        assert!(select_reference(&records(), unsupported, true).is_err());
    }
}

#[test]
fn reference_preserves_source_and_original_word_positions() {
    let mut rows = records();
    let row = rows
        .iter_mut()
        .find(|r| r.surah == 67 && r.ayah == 1)
        .unwrap();
    row.text_uthmani = "  alpha beta gamma delta café item  ".into();
    let before: Vec<_> = rows.iter().map(|r| r.text_uthmani.clone()).collect();
    let selected = select_reference(&rows, 67, false).unwrap();
    assert_eq!(selected[0].source, "  alpha beta gamma delta café item  ");
    assert_eq!(selected[0].words[0].position, 5);
    assert_eq!(selected[0].words[0].text, "café");
    assert_eq!(
        before,
        rows.iter()
            .map(|r| r.text_uthmani.clone())
            .collect::<Vec<_>>()
    );
    assert_eq!(normalize("أ إ آ ٱ، ـtest!"), ["ا", "ا", "ا", "ا", "test"]);
}

#[test]
fn standalone_pause_marks_are_not_counted_as_words_and_display_stays_unchanged() {
    let mut rows = records();
    rows.iter_mut()
        .find(|r| r.surah == 67 && r.ayah == 2)
        .unwrap()
        .text_uthmani = "oak ۚ pine ۖ ۙ ۜ ۞".into();
    let selected = passage(&rows, 67, 2, 2, false).unwrap();
    assert_eq!(selected[0].source, "oak ۚ pine ۖ ۙ ۜ ۞");
    assert_eq!(selected[0].words.len(), 2);
    assert_eq!(selected[0].words[0].text, "oak");
    assert_eq!(selected[0].words[0].position, 1);
    assert_eq!(selected[0].words[1].text, "pine");
    assert_eq!(selected[0].words[1].position, 2);
    let result = compare(&selected, "oak pine");
    assert_eq!(result.status, "tentative");
    assert!(result.skips.is_empty());
}

#[test]
fn opening_only_appears_when_the_selected_range_contains_it() {
    let rows = records();
    let with = passage(&rows, 112, 1, 2, true).unwrap();
    assert_eq!(with.len(), 3);
    assert_eq!(with[0].id, VerseId::Label("opening".into()));
    assert_eq!(passage(&rows, 112, 1, 2, false).unwrap().len(), 2);
    let later = passage(&rows, 112, 2, 3, true).unwrap();
    assert_eq!(later.len(), 2);
    assert_eq!(later[0].id, VerseId::Number(2));
    assert_eq!(later[1].id, VerseId::Number(3));
    assert_eq!(passage(&rows, 1, 1, 1, false).unwrap()[0].words.len(), 4);
}

#[test]
fn malformed_source_and_ranges_fail_closed() {
    for (first, last) in [(0, 1), (3, 2), (1, 5), (u32::MAX, u32::MAX)] {
        assert!(passage(&records(), 112, first, last, true).is_err());
    }
    let mut rows = records();
    rows.retain(|r| !(r.surah == 67 && r.ayah == 20));
    assert!(select_reference(&rows, 67, false).is_err());
    let mut rows = records();
    rows.iter_mut()
        .find(|r| r.surah == 112 && r.ayah == 1)
        .unwrap()
        .text_uthmani = "wrong boundary words here tail".into();
    assert!(select_reference(&rows, 112, false).is_err());
    let mut rows = records();
    rows.push(Record {
        surah: 1,
        ayah: 1,
        text_uthmani: "alpha beta gamma delta".into(),
    });
    assert!(select_reference(&rows, 112, false).is_err());
}

#[test]
fn passage_word_budget_is_enforced() {
    let mut rows = records();
    rows.iter_mut()
        .find(|r| r.surah == 112 && r.ayah == 2)
        .unwrap()
        .text_uthmani = vec!["token"; 101].join(" ");
    assert!(passage(&rows, 112, 2, 2, false).is_err());
}

#[test]
fn seeded_random_selection_is_repeatable_and_stays_inside_scope() {
    let data: Vec<_> = records()
        .iter()
        .map(|r| {
            serde_json::json!({
                "surah": r.surah, "ayah": r.ayah, "text_uthmani": r.text_uthmani,
            })
        })
        .collect();
    let input = serde_json::to_string(&data).unwrap();
    for seed in [0, 1, 29, 430, 431, u32::MAX] {
        for length in 1..=3 {
            let chosen = hifz_core::choose_json(&input, "[67,77]", seed, length).unwrap();
            assert_eq!(
                chosen,
                hifz_core::choose_json(&input, "[67,77]", seed, length).unwrap()
            );
            let value: serde_json::Value = serde_json::from_str(&chosen).unwrap();
            let surah = value["surah"].as_u64().unwrap() as u32;
            let first = value["first"].as_u64().unwrap() as u32;
            let last = value["last"].as_u64().unwrap() as u32;
            assert!([67, 77].contains(&surah));
            assert!(first >= 1 && first <= last);
            assert!(last <= verse_count(surah).unwrap());
            assert!(last - first < length);
            assert!(passage(&records(), surah, first, last, false).is_ok());
        }
    }
}

#[test]
fn one_clear_interior_skip_and_short_final_repeat_are_tentative() {
    let source = vec![verse(7, "alpha beta gamma delta"), verse(8, "epsilon zeta")];
    let skipped = compare(&source, "alpha gamma delta epsilon zeta");
    assert_eq!(skipped.status, "tentative");
    assert_eq!(skipped.pronunciation, "unsure");
    assert_eq!(skipped.skips.len(), 1);
    assert_eq!(skipped.skips[0].verse, VerseId::Number(7));
    assert_eq!(skipped.skips[0].position, 2);
    let repeated = compare(&source, "alpha beta gamma delta epsilon zeta epsilon zeta");
    assert_eq!(repeated.status, "tentative");
    assert_eq!(repeated.repeats, [VerseId::Number(8)]);
    assert_eq!(repeated.outside_words, 0);
}

#[test]
fn substitutions_ambiguous_skips_and_incomplete_passages_have_no_accusations() {
    let source = vec![verse(1, "alpha beta gamma delta epsilon")];
    for text in [
        "",
        "alpha beta unknown delta epsilon",
        "beta gamma delta epsilon",
        "alpha beta gamma delta",
        "unknown",
    ] {
        assert_unsure(&source, text);
    }
    assert_unsure(
        &[verse(1, "alpha beta beta gamma delta")],
        "alpha beta gamma delta",
    );
    assert_unsure(&source, &"x".repeat(5001));
    assert_unsure(&source, &vec!["alpha"; 201].join(" "));
    assert_unsure(&[verse(1, &vec!["alpha"; 101].join(" "))], "alpha");
}

#[test]
fn exact_words_do_not_claim_pronunciation_and_closing_words_are_unassessed() {
    let source = vec![verse(1, "alpha beta gamma delta")];
    for (text, closing) in [
        ("alpha beta gamma delta", 0),
        ("alpha beta gamma delta closing", 1),
        ("alpha beta gamma delta closing tail", 2),
    ] {
        let result = compare(&source, text);
        assert_eq!(result.status, "tentative");
        assert_eq!(result.pronunciation, "unsure");
        assert_eq!(result.outside_words, closing);
        assert!(result.skips.is_empty());
        assert!(result.repeats.is_empty());
    }
}
