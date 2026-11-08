const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = value => escape(JSON.stringify(value, null, 2));
const labels = {ATTACK_SUCCEEDED:'Attack succeeded', RESISTED:'Resisted', AGENT_STOPPED:'Agent stopped', NOT_EXPOSED:'Not exposed', ERROR:'Execution error'};
let state, current, selectedResult = 0, timer;
const selected = new Set();
async function request(path, data) {
  const response = await fetch(path, data ? {method:'POST', headers:{'Content-Type':'application/json','X-Scanner-Token':state.token}, body:JSON.stringify(data)} : {});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Request failed');
  return body;
}
function notify(error) { $('notice').textContent = error.message || error; $('notice').hidden = false; }
function renderAttacks() {
  const filter = $('filter').value.toLowerCase();
  $('attacks').innerHTML = state.attacks.filter(a => JSON.stringify(a).toLowerCase().includes(filter)).map(a => `<div class="attack"><label class="attack-head"><input type="checkbox" data-attack="${escape(a.id)}" ${selected.has(a.id)?'checked':''}><span><strong>${escape(a.id.replace(/_/g,' '))}</strong><small>${escape(a.type.replace(/_/g,' '))} · ${a.tools.length} tools</small></span></label><details><summary>Task, tools & success criteria</summary><p>${escape(a.description)}</p><p><b>Task:</b> ${escape(a.task)}</p><p><b>Tools:</b> ${escape(a.tools.map(t=>t.name).join(', '))}</p><pre>${pretty({success_any:a.success_any,task_check:a.task_check})}</pre><details><summary>Full attack content</summary><pre>${pretty(a.tools)}</pre></details></details></div>`).join('');
  $('selection-count').textContent = `${selected.size} scenarios selected`;
  $('launch').disabled = !selected.size;
}
function connectionHint() {
  const mode = $('mode').value;
  $('command-label').hidden = mode !== 'custom';
  $('connection-hint').textContent = mode === 'demo' ? 'Explore the full workflow without credentials. This scripted demo deliberately follows one attack; it is not a model evaluation.' : mode === 'gemini' ? 'Uses GEMINI_API_KEY and optional AGENT_MODEL from the server environment. Requests may incur provider charges.' : 'Your local command runs once per test with a task and simulated MCP tools. Use an adapter compatible with the scanner contract.';
}
function renderHistory() {
  $('history').innerHTML = state.scans.map(s=>`<button class="history-item" data-scan="${escape(s.id)}">${escape(s.name)}<small>${escape(s.status.toUpperCase())} · ${new Date(s.started_at).toLocaleDateString()}</small></button>`).join('') || '<p class="muted">Your scans will appear here.</p>';
}
async function refreshHistory() { const fresh=await request('/api/bootstrap'); state.scans=fresh.scans; renderHistory(); }
function showSetup() { clearTimeout(timer); $('setup').hidden=false; $('results').hidden=true; $('breadcrumb').textContent='New scan'; $('notice').hidden=true; }
function evidence(index) {
  selectedResult=index;
  const r=current.results[index];
  if(!r) { $('evidence').innerHTML='<h2>Waiting for evidence.</h2><p class="muted">Results appear as each test finishes.</p>'; return; }
  document.querySelectorAll('.result').forEach((el,i)=>el.setAttribute('aria-pressed',String(i===index)));
  $('evidence').innerHTML=`<h2>${escape(r.attack_id.replace(/_/g,' '))}</h2><span class="badge ${r.outcome}">${labels[r.outcome]}</span><h3>LEGITIMATE TASK</h3><p>${escape(r.attack?.task || '')}</p><h3>RECORDED TOOL CALLS</h3>${r.calls.length?r.calls.map((c,i)=>`<div class="trace"><code>${i+1}. ${escape(c.tool)}</code><pre>${pretty(c.args)}</pre></div>`).join(''):'<p class="muted">No tool calls recorded.</p>'}${r.evidence?`<h3>MATCHED ATTACK EVIDENCE</h3><pre>${pretty(r.evidence)}</pre>`:''}<h3>FINAL ANSWER</h3><pre>${escape(r.answer || '(No final answer)')}</pre>${r.stderr?`<h3>EXECUTION DIAGNOSTICS</h3><pre>${escape(r.stderr)}</pre>`:''}<details><summary>Attack definition & scoring rules</summary><pre>${pretty(r.attack)}</pre></details><p class="muted">“Resisted” means no attack rule matched and the answer passed this scenario’s phrase check. It is not a general security guarantee.</p>`;
}
function renderScan() {
  $('setup').hidden=true; $('results').hidden=false;
  $('breadcrumb').textContent='Scan results';
  $('scan-title').textContent=current.name;
  $('scan-meta').textContent=`${current.status.toUpperCase()} / ${new Date(current.started_at).toLocaleString()}`;
  $('demo-banner').hidden=current.mode!=='demo';
  $('progress').innerHTML=`${current.results.length} of ${current.total} tests finished · ${escape(current.error || (current.status==='running'?'Testing in progress. You can inspect completed results.':current.status==='interrupted'?'Run interrupted. Replay to start a fresh scan.':'All selected tests finished.'))}<progress max="${current.total}" value="${current.results.length}"></progress>`;
  $('stats').innerHTML=Object.entries(labels).map(([key,label])=>`<div class="stat"><b>${current.results.filter(r=>r.outcome===key).length}</b><small>${label}</small></div>`).join('');
  $('result-list').innerHTML=current.results.map((r,i)=>`<button class="result" data-result="${i}"><strong>${escape(r.attack_id.replace(/_/g,' '))}</strong><span class="badge ${r.outcome}">${labels[r.outcome]}</span> <small class="muted">Run ${r.iteration}</small></button>`).join('') || '<p class="muted">The first test is running…</p>';
  $('replay').disabled=current.status==='running';
  evidence(selectedResult);
}
async function openScan(id, reset=true) {
  clearTimeout(timer);
  try { current=await request(`/api/scans/${id}`); if(reset) selectedResult=0; renderScan();
    if(current.status==='running') timer=setTimeout(()=>openScan(id,false),1500);
    else await refreshHistory();
  } catch(error) { notify(error); }
}
async function launch(data) {
  $('notice').hidden=true; $('launch').disabled=true; $('replay').disabled=true;
  try { const scan=await request('/api/scans',data); await refreshHistory(); await openScan(scan.id); }
  catch(error) { notify(error); }
  finally { $('launch').disabled=!selected.size; if(current) $('replay').disabled=current.status==='running'; }
}
$('launch').onclick=()=>launch({name:$('agent-name').value || 'My agent', mode:$('mode').value, command:$('command').value, attacks:[...selected],repeat:Number($('repeat').value)});
$('replay').onclick=()=>launch({name:current.name,mode:current.mode,command:current.command,attacks:current.attacks,repeat:current.repeat});
$('new-scan').onclick=showSetup;
$('filter').oninput=renderAttacks;
$('mode').onchange=connectionHint;
$('select-all').onclick=()=>{ if(selected.size===state.attacks.length) selected.clear(); else state.attacks.forEach(a=>selected.add(a.id)); renderAttacks(); };
$('attacks').onchange=event=>{ const id=event.target.dataset.attack; if(id){event.target.checked?selected.add(id):selected.delete(id); $('selection-count').textContent=`${selected.size} scenarios selected`; $('launch').disabled=!selected.size;} };
$('history').onclick=event=>{const item=event.target.closest('[data-scan]'); if(item)openScan(item.dataset.scan);};
$('result-list').onclick=event=>{const item=event.target.closest('[data-result]');if(item)evidence(Number(item.dataset.result));};
$('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`scan-${current.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
(async()=>{try{state=await request('/api/bootstrap');state.attacks.forEach(a=>selected.add(a.id));renderAttacks();renderHistory();connectionHint();const running=state.scans.find(s=>s.status==='running');if(running)await openScan(running.id);}catch(error){notify(error);}})();
