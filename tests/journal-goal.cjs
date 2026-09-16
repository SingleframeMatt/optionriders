const fs = require('fs'), vm = require('vm'), assert = require('assert');
const path = require('path');
const sourcePath = process.argv[2] || path.join(__dirname, '..', 'journal.js');
const elements = new Map();
const storage = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {value:'',textContent:'',innerHTML:'',disabled:false,
    setAttribute(k,v){this[k]=v},reportValidity(){return true}});
  return elements.get(id);
};
const context = vm.createContext({console, Intl, Date, Number, Math, JSON, setTimeout,
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
  document:{getElementById:element},window:{},});
vm.runInContext(fs.readFileSync(sourcePath,'utf8').split('document.addEventListener("DOMContentLoaded", async () => {')[0],context);
const run = code => vm.runInContext(code,context);
const text = id => element(id).textContent;
(async()=>{
  run('loadGoalSettings()');
  assert.equal(text('goalDailyPreview'),'£250 / day');
  element('goalMonthlyInput').value='6000';element('goalDaysInput').value='24';
  await run('saveGoalSettings({preventDefault(){}})');
  assert.equal(run('state.monthlyTarget'),6000);
  assert.equal(run('state.tradingDays'),24);
  assert.equal(text('whyWeeklyTarget'),'£1,250');assert.equal(text('whyYearTarget'),'£72,000');
  run('state.monthlyTarget=1; state.goalSettingsVersion=null; loadGoalSettings()');
  assert.equal(run('state.monthlyTarget'),6000);
  run('state.fxRate=0.8; renderGoalPie(3750)');
  assert.equal(text('goalPct'),'50% of goal');
  assert.equal((element('goalRewards').innerHTML.match(/brick brick-laid/g)||[]).length,12);
  run('renderGoalPie(7500)');assert.equal(text('goalPct'),'100% of goal');
  assert.equal((element('goalRewards').innerHTML.match(/brick brick-laid/g)||[]).length,24);
  run('renderGoalPie(-100)');assert.match(text('goalNote'),/break even/);
  run('renderGoalPie(0)');assert.match(text('goalNote'),/daily target/);
  for (const value of [0,-1,NaN,Infinity,1000000000]) assert.equal(run(`validGoalSettings({monthlyTarget:${value},tradingDays:20})`),null);
  for (const value of [0,-1,1.5,32]) assert.equal(run(`validGoalSettings({monthlyTarget:5000,tradingDays:${value}})`),null);
  run(`_supabase={auth:{updateUser:async ({data})=>({data:{user:{id:'alice',user_metadata:data}},error:null})}};
    _session={user:{id:'alice',user_metadata:{journal_goal_GBP:{monthlyTarget:8000,tradingDays:16}}}};
    loadGoalSettings();`);
  assert.equal(text('goalDailyPreview'),'£500 / day');
  element('goalMonthlyInput').value='9000';element('goalDaysInput').value='18';
  run('loadGoalSettings()');assert.equal(element('goalMonthlyInput').value,'9000'); // repeated auth events preserve drafts
  await run('saveGoalSettings({preventDefault(){}})');
  assert.equal(run('_session.user.user_metadata.journal_goal_GBP.monthlyTarget'),9000);
  assert.match(text('goalSaveStatus'),/saved to your account/);
  run("_session={user:{id:'bob',user_metadata:{}}};state.lastGoalPnl=null;loadGoalSettings()");
  assert.equal(run('state.monthlyTarget'),5000);assert.equal(text('goalPct'),'—');
  run("_supabase.auth.updateUser=async()=>({error:new Error('offline')})");
  element('goalMonthlyInput').value='10000';await run('saveGoalSettings({preventDefault(){}})');
  assert.equal(run('state.monthlyTarget'),5000);assert.match(text('goalSaveStatus'),/Not saved/);
  run("_session={user:{id:'alice',user_metadata:{journal_goal_GBP:{monthlyTarget:9000,tradingDays:18}}}};state.currency='EUR';loadGoalSettings()");
  assert.equal(run('state.monthlyTarget'),5000);assert.equal(text('goalDailyPreview'),'€250 / day');
  run("_session=null;loadGoalSettings()");assert.equal(run('state.monthlyTarget'),5000);
  console.log('Passed: daily/weekly/yearly targets, local persistence, account save/isolation, currency isolation, FX progress, brick counts, input validation, failed saves, draft preservation.');
})().catch(e=>{console.error(e);process.exit(1)});
