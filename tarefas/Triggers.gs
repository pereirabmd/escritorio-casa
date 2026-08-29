function instalarTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'jobPeriodico') {
      ScriptApp.deleteTrigger(t);
    }
  });

  ScriptApp.newTrigger('jobPeriodico')
    .timeBased()
    .everyHours(1)
    .create();
}
