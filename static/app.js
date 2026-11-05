'use strict';
const $ = s => document.querySelector(s);
const state = {connections:null, money:null, moneyTab:'transactions', history:[], busy:false};
const currency = p => p === null ? '—' : new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP'}).format(p/100);
const today = () => {const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function button(text,action,cls='secondary'){const b=node('button',text,cls);b.type='button';b.addEventListener('click',()=>guard(action));return b;}
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,7000);}
async function guard(fn){try{await fn();}catch(error){toast(error.message);}}
async function api(path,body){let response;try{response=await fetch('/api'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Oracle-Request':'local-dashboard'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(path==='/chat'?180000:40000)});}catch{throw new Error('Oracle is not responding. Check that oracle.py is still running, then retry.');}const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Check the form values and try again.');return data;}
function navigate(){const name=['home','chat','money','devices','connections'].includes(location.hash.slice(1))?location.hash.slice(1):'home';document.querySelectorAll('.page').forEach(p=>p.hidden=p.id!=='page-'+name);document.querySelectorAll('[data-nav]').forEach(a=>{a.classList.toggle('active',a.dataset.nav===name);if(a.dataset.nav===name)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});$('#breadcrumb').textContent='Workspace / '+({home:'Overview',chat:'Ask Oracle',money:'MyMoney',devices:'Devices',connections:'Connections'}[name]);if(name==='home')loadDeviceOverview();if(name==='money')guard(loadMoney);if(name==='devices'){guard(loadDevices);loadMonitoringCards();}if(name==='connections')guard(loadConnections);}
window.addEventListener('hashchange',navigate);
$('#today').textContent=new Intl.DateTimeFormat('en-GB',{weekday:'long',day:'numeric',month:'long'}).format(new Date()).toUpperCase()+' / YOUR PERSONAL WORKSPACE';

let checking=false;
async function loadConnections(){if(checking)return;checking=true;$('#check-connections').disabled=true;try{state.connections=await api('/connections');renderConnections();}catch(e){const alert=$('#global-alert');alert.replaceChildren(node('span',e.message),button('Retry',loadConnections));alert.hidden=false;}finally{checking=false;$('#check-connections').disabled=false;}}
function renderConnections(){const data=state.connections;const names={llm:'AI provider',google:'Google Workspace',iot:'Home Assistant'};const errors=['llm','google','iot'].filter(k=>data[k].status==='error');const alert=$('#global-alert');alert.replaceChildren();alert.hidden=!errors.length;if(errors.length){alert.append(node('span',errors.map(k=>names[k]+': '+data[k].message).join(' ')));const link=node('a','Fix connections ↗');link.href='#connections';alert.append(link);}$('#connection-count').hidden=!errors.length;$('#connection-count').textContent=errors.length;const grid=$('#connection-cards');grid.replaceChildren();for(const key of ['llm','google','iot']){const info=data[key];const card=node('article',undefined,'connection-card');card.append(node('h2',names[key]),node('span',({ready:'Connected',error:'Needs attention',unchecked:'Not tested',demo:'Demo mode'})[info.status]||info.status,'badge '+info.status),node('p',info.message));if(key==='llm')card.append(node('span',info.model,'fine-print'));const actions=node('div',undefined,'actions');actions.append(button('Configure',()=>connectionForm(key)));if(key==='llm')actions.append(button('Test API',async()=>{if(!confirm('Send a short test request to your AI provider? This may use a small amount of API credit.'))return;toast('Testing model access…');const result=await api('/connections/test-llm',{});toast(result.message);await loadConnections();}));if(key==='google'){actions.append(button('Reconnect Google',async()=>{const result=await api('/google/connect',{});location.assign(result.url);},'primary'));actions.append(button('Disconnect',async()=>{if(confirm('Disconnect Google from Oracle?')){await api('/google/disconnect',{});await loadConnections();}}));}if(key==='iot')actions.append(button('Retry',loadConnections));card.append(actions);grid.append(card);}}
$('#check-connections').addEventListener('click',loadConnections);$('#refresh-all').addEventListener('click',loadConnections);

let modalSave;
function openForm(title,fields,save,help=''){const form=$('#modal-form');form.reset();$('#form-title').textContent=title;$('#form-help').textContent=help;$('#form-error').textContent='';$('#form-fields').replaceChildren();for(const field of fields){const [name,label,value='',type='text',choices]=field;const wrap=node('label',label);let input;if(choices){input=node('select');for(const option of choices){const o=node('option',option);o.value=option;input.append(o);}}else{input=node('input');input.type=type;}input.name=name;input.value=value??'';input.autocomplete=type==='password'?'new-password':'off';if(type==='password')input.placeholder='Leave blank to keep existing';wrap.append(input);$('#form-fields').append(wrap);}modalSave=save;$('#form-dialog').showModal();}
$('#close-dialog').onclick=()=>$('#form-dialog').close();$('#cancel-dialog').onclick=()=>$('#form-dialog').close();
$('#modal-form').addEventListener('submit',async e=>{e.preventDefault();$('#save-form').disabled=true;$('#form-error').textContent='';try{await modalSave(Object.fromEntries(new FormData(e.target)));$('#form-dialog').close();toast('Saved locally.');}catch(error){$('#form-error').textContent=error.message;}finally{$('#save-form').disabled=false;}});
function connectionForm(provider){const c=state.connections?.configuration||{};const fields={llm:[['OPENAI_API_KEY','API key','','password'],['OPENAI_MODEL','Model',c.model||'gpt-4o-mini'],['OPENAI_BASE_URL','API base URL (blank = OpenAI)',c.base_url||'']],google:[['GOOGLE_CLIENT_ID','Google client ID','','password'],['GOOGLE_CLIENT_SECRET','Google client secret','','password'],['GOOGLE_REDIRECT_URI','Authorized redirect URI',c.redirect_uri||'http://127.0.0.1:8000/api/google/callback']],iot:[['IOT_BACKEND','Backend',c.iot_backend||'demo','text',['demo','home_assistant']],['HA_URL','Home Assistant URL (leave blank to keep)'],['HA_TOKEN','Access token','','password'],['HA_ALLOWED_ENTITIES','Allowed entity IDs, separated by commas (blank keeps existing)']]};openForm('Configure '+({llm:'AI provider',google:'Google',iot:'devices'})[provider],fields[provider],async values=>{await api('/connections/configure',{provider,values});await loadConnections();},provider==='google'?'Register this exact redirect URI in Google Cloud → OAuth client → Authorized redirect URIs. Save, then click Reconnect Google.':'Credentials stay in your local .env file. Blank secrets keep existing values.');}

function addMessage(role,content){$('.chat-empty')?.remove();const el=node('article',undefined,'message '+role);el.append(node('strong',role==='user'?'YOU':'ORACLE'),node('div',content));$('#chat-log').append(el);$('#chat-log').scrollTop=$('#chat-log').scrollHeight;return el;}
async function sendChat(text){if(state.busy)return;state.busy=true;$('#send-chat').disabled=true;$('#chat-input').value='';addMessage('user',text);$('#chat-state').textContent='Oracle is thinking…';try{const shareDevices=$('#share-devices').checked;$('#share-devices').checked=false;const result=await api('/chat',{message:text,history:state.history.slice(-20),share_devices:shareDevices});addMessage('assistant',result.reply);if(!shareDevices)state.history.push({role:'user',content:text},{role:'assistant',content:result.reply});state.history=state.history.slice(-20);if(result.needs_confirmation)toast('Review Oracle’s proposed action before confirming in chat.');}catch(error){addMessage('assistant',error.message);$('#chat-input').value=text;}finally{state.busy=false;$('#send-chat').disabled=false;$('#chat-state').textContent='Your messages are sent to your AI provider.';loadConnections();}}
$('#chat-form').addEventListener('submit',e=>{e.preventDefault();const text=$('#chat-input').value.trim();if(text)sendChat(text);});
$('#chat-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#chat-form').requestSubmit();}});
$('#hero-form').addEventListener('submit',e=>{e.preventDefault();const text=$('#hero-input').value.trim();if(!text)return;location.hash='chat';$('#hero-input').value='';sendChat(text);});
document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>{location.hash='chat';$('#chat-input').value=b.dataset.prompt;$('#chat-input').focus();});
$('#clear-chat').onclick=()=>{if(state.busy){toast('Wait for the current reply before clearing.');return;}if(confirm('Clear this browser session’s conversation?')){state.history=[];$('#chat-log').replaceChildren();}};
const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
$('#dictate').onclick=()=>{if(!SpeechRecognition){toast('Dictation is not supported in this browser. Use Chrome or Edge, or type your message.');return;}if(!confirm('Use browser speech recognition? Your browser may send audio to its speech provider. The transcript stays a draft until you send it.'))return;const recognition=new SpeechRecognition();recognition.lang='en-GB';recognition.onresult=e=>{$('#chat-input').value=e.results[0][0].transcript;};recognition.onerror=e=>toast('Microphone unavailable or speech not recognized ('+e.error+'). Check browser microphone permissions.');recognition.start();};

async function loadDevices(){const target=$('#device-list');try{const result=await api('/devices');$('#device-mode').textContent=result.simulated?'Demo mode. These devices are simulated; no physical hardware is controlled.':'Connected to your allowlisted Home Assistant devices.';state.devices=result.devices;target.replaceChildren();if(!result.devices.length)target.append(node('p','No allowlisted devices. Add entity IDs in Connections.','empty'));for(const device of result.devices){const card=node('article',undefined,'essential');card.append(node('span',result.simulated?'SIMULATED DEVICE':'CONNECTED DEVICE','tiny'),node('h3',device.entity_id.replaceAll('_',' ')),node('div',readingValue(device),'device-state'));if(/^(light|switch)\./.test(device.entity_id)){const controls=node('div',undefined,'device-actions');for(const [label,action] of [['Turn on','turn_on'],['Turn off','turn_off']])controls.append(button(label,async()=>{if(!result.simulated&&!confirm(label+' '+device.entity_id+'?'))return;await api('/devices/control',{entity_id:device.entity_id,action});await loadDevices();}));card.append(controls);}target.append(card);}}catch(error){target.replaceChildren(node('p',error.message,'empty'),button('Open Connections',()=>location.hash='connections'));}}
function readingValue(reading) {
    return [reading.state, reading.unit].filter(Boolean).join(' ');
}
function renderMonitoringCards(result) {
    const target = $('#monitoring-cards');
    target.replaceChildren();
    if (!result.panels.length) target.append(node('p', 'No monitoring cards for this connection.'));
    for (const panel of result.panels) {
        const card = node('article', undefined, 'essential');
        card.append(node('span', result.simulated ? 'SIMULATED' : 'HOME ASSISTANT', 'tiny'),
            node('h3', panel.title), node('p', panel.device.entity_id),
            node('div', readingValue(panel.device), 'device-state'));
        const history = node('details');
        history.append(node('summary', 'Recent saved readings'));
        if (!panel.readings.length) history.append(node('p', 'Capture readings to start a history.'));
        const list = node('ul');
        for (const reading of panel.readings) {
            list.append(node('li', new Date(reading.captured_at).toLocaleString() + ' · ' + readingValue(reading)));
        }
        history.append(list);
        card.append(history, button('Ask about this device', () => {
            location.hash = 'chat';
            $('#chat-input').value = 'Summarise the latest state and saved readings for ' + panel.device.entity_id + '.';
            $('#share-devices').checked = true;
            $('#chat-input').focus();
        }), button('Remove card', async () => {
            if (!confirm('Remove this monitoring card and its saved readings?')) return;
            await api('/devices/workspace/cards/' + panel.id + '/remove', {});
            await loadMonitoringCards();
        }));
        target.append(card);
    }
}
async function loadMonitoringCards() {
    try { renderMonitoringCards(await api('/devices/workspace')); }
    catch (error) { $('#monitoring-cards').replaceChildren(node('p', error.message)); }
}
async function loadDeviceOverview() {
    const target = $('#overview-devices');
    try {
        const result = await api('/devices/workspace');
        target.replaceChildren();
        for (const panel of result.panels.slice(0, 4)) {
            const link = node('a', undefined, 'essential');
            link.href = '#devices';
            link.append(node('span', result.simulated ? 'SIMULATED READING' : 'DEVICE READING', 'tiny'),
                node('h3', panel.title), node('p', readingValue(panel.device)));
            target.append(link);
        }
    } catch { target.replaceChildren(); }
}
$('#refresh-devices').onclick = () => guard(async () => { await loadDevices(); await loadMonitoringCards(); });
$('#capture-device-sample').onclick = () => guard(async () => {
    renderMonitoringCards(await api('/devices/workspace/sample', {}));
    toast('Readings captured for available monitoring cards.');
});
$('#add-device-card').onclick = () => guard(async () => {
    const result = await api('/devices');
    const ids = result.devices.map(device => device.entity_id);
    if (!ids.length) throw new Error('Add devices to the allowlist in Connections first.');
    openForm('Save a monitoring card', [['entity_id','Device',ids[0],'text',ids], ['title','Card title']], async values => {
        await api('/devices/workspace/cards', values);
        await loadMonitoringCards();
    }, 'Select an existing entity to create its card or update its title.');
});

async function loadMoney(){state.money=await api('/money');renderMoney();}
function renderMoney(){const s=state.money.summary;$('#money-notices').replaceChildren(...s.notices.map(n=>node('div',n)));const stats=$('#money-stats');stats.replaceChildren();for(const [label,value] of [['Bank balance',s.balance],['Available after reserves',s.spendable],['Daily allowance',s.daily],['Next 7 days',s.weekly]]){const card=node('div',undefined,'stat');card.append(node('span',label),node('strong',currency(value)));stats.append(card);}const segments=[['Bills',s.commitments,'#cb9b69'],['Savings',s.reserved,'#989ac2'],['Safety buffer',s.buffer,'#759ab0'],['Spendable',s.spendable,'#709379']];const total=segments.reduce((sum,x)=>sum+x[1],0)||1;$('#budget-bar').replaceChildren();$('#budget-legend').replaceChildren();for(const [name,value,color] of segments){const bar=node('div');bar.style.width=(value/total*100)+'%';bar.style.background=color;bar.title=name+': '+currency(value);$('#budget-bar').append(bar);const legend=node('span');const swatch=node('i',undefined,'swatch');swatch.style.background=color;legend.append(swatch,node('span',name+' '+currency(value)));$('#budget-legend').append(legend);}renderMoneyTable();}
const titles={transactions:'Transactions',pending:'Upcoming payments & receipts',schedules:'Bills & expected income',pots:'Savings pots',forecast:'90-day forecast',movements:'Savings allocation history'};
function renderMoneyTable(){const kind=state.moneyTab;document.querySelectorAll('[data-money-tab]').forEach(b=>b.classList.toggle('active',b.dataset.moneyTab===kind));$('#money-table-title').textContent=titles[kind];const add=$('#money-add');const adds={transactions:['Add transaction','transaction'],pending:['Add bill / income','schedule'],schedules:['Add bill / income','schedule'],pots:['New savings pot','pot']};add.hidden=!adds[kind];if(adds[kind]){add.textContent=adds[kind][0];add.onclick=()=>moneyForm(adds[kind][1]);}const target=$('#money-table');target.replaceChildren();$('#forecast-chart').hidden=kind!=='forecast';let columns,rows;const d=state.money;if(kind==='transactions'){columns=['Date','Description','Amount','Category','Actions'];rows=d.transactions.map(r=>[r.day,r.name,currency(r.amount),r.category,[button('Edit',()=>moneyForm('transaction',r)),button('Delete',()=>confirmedMoney('delete_transaction',{id:r.id},'Delete this transaction? Linked payments become unpaid again.'))]]);}if(kind==='pending'){columns=['Due','Description','Type','Amount','Actions'];rows=d.summary.pending.map(r=>[r.due,r.name,r.kind+(r.estimated?' · estimated':''),currency(r.amount),[button('Record paid / received',()=>confirmedMoney('settle',{id:r.id,due:r.due},'Has this money actually been paid or received? This changes your bank balance today.'))]]);}if(kind==='schedules'){columns=['Name','Type','Amount','First unpaid date','Frequency','Actions'];rows=d.schedules.map(r=>[r.name,r.kind+(r.estimated?' · estimated':''),currency(r.amount),r.start,r.frequency,[button('Stop',()=>confirmedMoney('stop_schedule',{id:r.id},'Remove all unpaid occurrences? Recorded transactions remain.'))]]);}if(kind==='pots'){columns=['Goal','Reserved','Target','Progress','Target date','Actions'];rows=d.pots.map(r=>{const progress=node('progress');progress.max=r.target;progress.value=r.reserved;progress.title=Math.floor(r.reserved*100/r.target)+'%';return[r.name,currency(r.reserved),currency(r.target),[progress],r.target_date||'—',[button('Allocate / release',()=>moneyForm('move_pot',r))]];});}if(kind==='movements'){columns=['Date','Pot','Movement'];rows=d.movements.map(r=>[r.day,r.name,currency(r.amount)]);}if(kind==='forecast'){columns=['Date','Closing balance','Low before income','Protected reserves','Shortfall'];rows=d.forecast.map(r=>[r.day,currency(r.balance),currency(r.low),currency(r.protected),currency(r.shortfall)]);drawForecast(d.forecast);}if(!rows.length){target.append(node('div','Nothing here yet. Add your first record to get started.','empty'));return;}const table=node('table');const head=node('thead');const tr=node('tr');columns.forEach(c=>tr.append(node('th',c)));head.append(tr);table.append(head);const body=node('tbody');for(const row of rows){const tr=node('tr');for(const value of row){const td=node('td');if(Array.isArray(value))td.append(...value);else td.textContent=value;tr.append(td);}body.append(tr);}table.append(body);target.append(table);}
function drawForecast(rows){const target=$('#forecast-chart');target.replaceChildren(node('p','Scheduled cashflow only. Teal: closing balance · Amber: protected reserves. Bills precede income on the same date.','muted'));const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 900 190');svg.setAttribute('role','img');svg.setAttribute('aria-label','90 day scheduled closing balance and protected reserves');const low=Math.min(0,...rows.map(r=>r.low));const high=Math.max(1,...rows.map(r=>Math.max(r.balance,r.protected)));for(const [key,color] of [['balance','#2d684d'],['protected','#cb9b69']]){const line=document.createElementNS(ns,'polyline');line.setAttribute('points',rows.map((r,i)=>`${10+i*880/(rows.length-1)},${175-(r[key]-low)/(high-low)*160}`).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke',color);line.setAttribute('stroke-width','3');svg.append(line);}target.append(svg);}
document.querySelectorAll('[data-money-tab]').forEach(b=>b.onclick=()=>{state.moneyTab=b.dataset.moneyTab;if(state.money)renderMoneyTable();});
document.querySelectorAll('[data-money-form]').forEach(b=>b.onclick=()=>moneyForm(b.dataset.moneyForm));
async function confirmedMoney(action,values,message){if(confirm(message)){await api('/money',{action,values});await loadMoney();}}
function moneyForm(action,row={}){const forms={reconcile:['Reconcile bank balance',[['balance','Actual bank balance (£)',state.money?state.money.summary.balance/100:'']],'Creates an adjustment transaction; never silently rewrites history.'],settings:['Payday & limits',[['payday','Next payday',state.money?.settings.payday||'','date'],['buffer','Safety buffer (£)',state.money?state.money.summary.buffer/100:0],['warning','Caution threshold (£)',state.money?state.money.settings.warning/100:200]],'Choose a future payday. Upcoming bills and reserved savings reduce spendable cash.'],transaction:['Record actual money',[['name','Description',row.name||''],['amount','Amount (£): negative for spending',row.amount!==undefined?row.amount/100:''],['day','Date',row.day||today(),'date'],['category','Category',row.category||'General']],'Use Upcoming → Record paid / received for a scheduled bill or income, to avoid counting it twice.'],schedule:['Plan a bill or income',[['name','Description'],['kind','Type','bill','text',['bill','income']],['amount','Positive amount (£)'],['start','First UNPAID due date',today(),'date'],['frequency','Frequency','monthly','text',['once','weekly','monthly','yearly']],['category','Category','General'],['estimated','Estimated amount?','no','text',['no','yes']]],'Expected income does not increase your real balance until you record receipt.'],pot:['Create a savings pot',[['name','Goal name'],['target','Target amount (£)'],['target_date','Target date (optional)','','date']],'Pots reserve cash inside your balance. They are not additional bank accounts.'],move_pot:['Allocate or release',[['amount','£: positive allocates, negative releases']],'This changes your reservation, not your bank balance.']};const [title,fields,help]=forms[action];openForm(title,fields,async values=>{if(row.id)values.id=row.id;await api('/money',{action,values});await loadMoney();},help);}
const googleResult=new URLSearchParams(location.search).get('google');if(googleResult){toast(googleResult==='connected'?'Google connected.':'Google sign-in failed or was cancelled. Check OAuth settings and reconnect.');history.replaceState(null,'',location.pathname+location.hash);}
navigate();loadConnections();setInterval(()=>{if(!document.hidden)loadConnections();},60000);
