// Keep startup recovery independent of the Rust engine and microphone code.
const load = document.getElementById('load');
const reload = document.getElementById('reload-app');
const status = document.getElementById('status');
let finished = false;
const failureMessage = 'The app could not finish loading. Check your connection, then reload. If this keeps happening, open this page in Chrome or Safari.';
function failed() {
  if (finished) return;
  finished = true;
  load.disabled = true;
  status.textContent = failureMessage;
  reload.hidden = false;
}
reload.addEventListener('click', () => location.reload());
const deadline = setTimeout(failed, 20000);
import('./app.js').then(() => {
  clearTimeout(deadline);
  if (finished) { load.disabled = true; reload.hidden = false; status.textContent = failureMessage; return; }
  finished = true;
}).catch(() => { clearTimeout(deadline); failed(); });
