import test from 'node:test';import assert from 'node:assert/strict';import {heatIndexC,buildPlan,safeParsePlans} from '../logic.js';
test('heat index returns air temperature below formula threshold',()=>assert.equal(heatIndexC(24,50),24));
test('heat index rises in hot humid conditions',()=>assert.ok(heatIndexC(35,70)>45));
test('heavy direct work with impermeable PPE escalates tier',()=>{const p=buildPlan({shiftName:'Test',startTime:'12:00',duration:4,temperature:38,humidity:60,intensity:'heavy',sun:'direct',ppe:'impermeable',acclimatized:false});assert.equal(p.tier,'severe');assert.ok(p.checklist.some(x=>x.includes('PPE')));});
test('invalid fields return helpful errors',()=>assert.throws(()=>buildPlan({shiftName:'',startTime:'',duration:0,temperature:70,humidity:0}),/shift name/i));
test('corrupt saved data safely becomes empty',()=>assert.deepEqual(safeParsePlans('{bad'),[]));
test('malformed saved entries are ignored',()=>assert.deepEqual(safeParsePlans('[null,{\"shiftName\":\"incomplete\"}]'),[]));

test('saved-plan validation rejects malformed nested data and caps history', () => {
  const valid = {
    shiftName:'Crew', startTime:'12:00', duration:4, temperature:34, humidity:68,
    intensity:'moderate', sun:'direct', ppe:'standard', acclimatized:false,
    heatIndex:45, tier:'high', label:'High concern', check:30, review:60,
    summary:'Summary', callout:'Callout', checklist:['Water'],
    timeline:[{time:'12:00', label:'Brief'}], createdAt:new Date().toISOString(),
  };
  assert.deepEqual(safeParsePlans(JSON.stringify([{...valid, timeline:[{time:'bad', label:'x'}]}])), []);
  assert.equal(safeParsePlans(JSON.stringify(Array.from({length:40}, () => valid))).length, 25);
});
