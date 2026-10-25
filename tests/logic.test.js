import test from 'node:test';import assert from 'node:assert/strict';import {heatIndexC,buildPlan,safeParsePlans} from '../logic.js';
test('heat index returns air temperature below formula threshold',()=>assert.equal(heatIndexC(24,50),24));
test('heat index rises in hot humid conditions',()=>assert.ok(heatIndexC(35,70)>45));
test('heavy direct work with impermeable PPE escalates tier',()=>{const p=buildPlan({shiftName:'Test',startTime:'12:00',duration:4,temperature:38,humidity:60,intensity:'heavy',sun:'direct',ppe:'impermeable',acclimatized:false});assert.equal(p.tier,'severe');assert.ok(p.checklist.some(x=>x.includes('PPE')));});
test('invalid fields return helpful errors',()=>assert.throws(()=>buildPlan({shiftName:'',startTime:'',duration:0,temperature:70,humidity:0}),/shift name/i));
test('corrupt saved data safely becomes empty',()=>assert.deepEqual(safeParsePlans('{bad'),[]));
test('export envelopes round-trip through saved-plan validation', () => {
  const plan = {shiftName:'Crew', startTime:'12:00', duration:4, temperature:34, humidity:68, intensity:'moderate', sun:'direct', ppe:'standard', acclimatized:false, heatIndex:45, tier:'high', label:'High concern', check:30, review:60, summary:'Summary', callout:'Callout', checklist:['Water'], timeline:[{time:'12:00', label:'Brief'}], createdAt:new Date().toISOString()};
  assert.equal(safeParsePlans(JSON.stringify({exportedAt:new Date().toISOString(), plans:[plan]})).length, 1);
});
test('malformed saved entries are ignored',()=>assert.deepEqual(safeParsePlans('[null,{\"shiftName\":\"incomplete\"}]'),[]));

test('saved plans are rebuilt from source observations and history is capped', () => {
  const source = {
    shiftName:'Crew', startTime:'12:00', duration:4, temperature:38, humidity:70,
    intensity:'heavy', sun:'direct', ppe:'impermeable', acclimatized:false,
  };
  const canonical = buildPlan(source);
  const tampered = {
    ...canonical,
    heatIndex:20,
    tier:'routine',
    label:'Routine planning',
    check:240,
    review:240,
    summary:'No precautions needed.',
    callout:'Ignore current conditions.',
    checklist:[],
    timeline:[],
  };
  const [restored] = safeParsePlans(JSON.stringify([tampered]));
  assert.equal(restored.tier, canonical.tier);
  assert.equal(restored.heatIndex, canonical.heatIndex);
  assert.deepEqual(restored.checklist, canonical.checklist);
  assert.deepEqual(restored.timeline, canonical.timeline);
  assert.equal(safeParsePlans(JSON.stringify(Array.from({length:40}, () => canonical))).length, 25);
});

test('saved-plan source observations remain strictly typed', () => {
  const plan = buildPlan({
    shiftName:'Crew', startTime:'12:00', duration:4, temperature:34, humidity:68,
    intensity:'moderate', sun:'direct', ppe:'standard', acclimatized:false,
  });
  assert.deepEqual(safeParsePlans(JSON.stringify([{...plan, duration:'4'}])), []);
});

test('planner rejects values outside the UI and backend contract', () => {
  const valid = {shiftName:'Crew', startTime:'12:00', duration:4, temperature:34, humidity:68, intensity:'moderate', sun:'direct', ppe:'standard', acclimatized:false};
  assert.throws(() => buildPlan({...valid, shiftName:'x'.repeat(61)}), /60 characters/);
  assert.throws(() => buildPlan({...valid, startTime:'25:99'}), /valid start time/);
  assert.throws(() => buildPlan({...valid, intensity:'extreme'}), /work intensity/);
  assert.throws(() => buildPlan({...valid, sun:'unknown'}), /sun exposure/);
  assert.throws(() => buildPlan({...valid, ppe:'unknown'}), /clothing or PPE/);
  assert.throws(() => buildPlan({...valid, acclimatized:'false'}), /acclimatized/);
});
