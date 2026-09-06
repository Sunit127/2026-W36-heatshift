export function heatIndexC(tempC, humidity) {
  if (!Number.isFinite(tempC) || !Number.isFinite(humidity)) throw new TypeError('Temperature and humidity must be numbers');
  const t = tempC * 9 / 5 + 32;
  if (t < 80 || humidity < 40) return Math.round(tempC * 10) / 10;
  let hi = -42.379 + 2.04901523*t + 10.14333127*humidity - .22475541*t*humidity - .00683783*t*t - .05481717*humidity*humidity + .00122874*t*t*humidity + .00085282*t*humidity*humidity - .00000199*t*t*humidity*humidity;
  if (humidity < 13 && t >= 80 && t <= 112) hi -= ((13-humidity)/4)*Math.sqrt((17-Math.abs(t-95))/17);
  if (humidity > 85 && t >= 80 && t <= 87) hi += ((humidity-85)/10)*((87-t)/5);
  return Math.round(((hi-32)*5/9)*10)/10;
}

export function buildPlan(input) {
  const temperature = Number(input.temperature), humidity = Number(input.humidity), duration = Number(input.duration);
  if (!input.shiftName?.trim()) throw new Error('Add a shift name.');
  if (!input.startTime) throw new Error('Choose a start time.');
  if (!(temperature >= 10 && temperature <= 60)) throw new Error('Temperature must be between 10°C and 60°C.');
  if (!(humidity >= 5 && humidity <= 100)) throw new Error('Humidity must be between 5% and 100%.');
  if (!(duration >= 1 && duration <= 16)) throw new Error('Shift length must be between 1 and 16 hours.');
  const hi = heatIndexC(temperature, humidity);
  let points = hi >= 41 ? 7 : hi >= 36 ? 5 : hi >= 31 ? 3 : hi >= 27 ? 1 : 0;
  points += {light:0, moderate:1, heavy:2}[input.intensity] ?? 0;
  points += {shade:0, mixed:1, direct:2}[input.sun] ?? 0;
  points += {breathable:0, standard:1, impermeable:3}[input.ppe] ?? 0;
  if (!input.acclimatized) points += 2;
  const tier = points >= 10 ? 'severe' : points >= 7 ? 'high' : points >= 4 ? 'caution' : 'routine';
  const config = {
    routine:{label:'Routine planning',check:60,review:120,summary:'Conditions still deserve a briefing. Keep water accessible and watch for changes.',callout:'Maintain normal heat precautions and reassess if the weather, workload, clothing, or worker condition changes.'},
    caution:{label:'Extra precautions',check:45,review:90,summary:'Several conditions can add heat strain. Increase supervision and protect recovery time.',callout:'Plan extra recovery in a cool or shaded area, keep drinking water close, and pair workers for symptom checks.'},
    high:{label:'High concern',check:30,review:60,summary:'The combination of heat and work demands needs an active control plan before starting.',callout:'Consider rescheduling heavy work, adding people or mechanical help, increasing recovery, and getting a supervisor heat-plan review.'},
    severe:{label:'Escalate before work',check:15,review:30,summary:'Multiple high-load factors are present. Do not rely on this tool as authorization to proceed.',callout:'Pause and escalate the plan. Use qualified local guidance to reduce exposure, reschedule, change PPE or workload, and define emergency response before work begins.'}
  }[tier];
  const checklist = ['Confirm cool drinking water is accessible','Identify the nearest cool or shaded recovery area','Name a buddy or supervisor for check-ins','Review early symptoms: headache, nausea, dizziness, weakness','Review emergency signs and how to call local emergency services'];
  if (!input.acclimatized) checklist.unshift('Give new or returning workers a gradual exposure plan');
  if (input.sun !== 'shade') checklist.push('Add shade and sun protection where practical');
  if (input.ppe === 'impermeable') checklist.push('Have a qualified person review PPE heat burden and recovery frequency');
  const timeline=[]; const [h,m]=input.startTime.split(':').map(Number); const start=h*60+m; const every=config.check;
  for(let minute=0;minute<=duration*60;minute+=every){const total=(start+minute)%1440;timeline.push({time:`${String(Math.floor(total/60)).padStart(2,'0')}:${String(total%60).padStart(2,'0')}`,label:minute===0?'Brief':minute%(config.review)===0?'Review plan':'Buddy check'});}
  return {...input,shiftName:input.shiftName.trim(),temperature,humidity,duration,heatIndex:hi,tier,...config,checklist,timeline,createdAt:new Date().toISOString()};
}

function isSavedPlan(value) { return value && typeof value === 'object' && typeof value.shiftName === 'string' && value.shiftName.trim() && typeof value.startTime === 'string' && /^\d{2}:\d{2}$/.test(value.startTime) && Number.isFinite(value.duration) && Number.isFinite(value.heatIndex) && typeof value.label === 'string' && Array.isArray(value.checklist) && Array.isArray(value.timeline); }
export function safeParsePlans(raw) { try { const value=JSON.parse(raw); return Array.isArray(value)?value.filter(isSavedPlan):[]; } catch { return []; } }
