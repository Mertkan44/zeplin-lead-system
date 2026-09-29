(function () {
  try {
    var saved = localStorage.getItem('zeplin_theme');
    document.documentElement.dataset.theme = saved === 'light' ? 'light' : 'dark';
  } catch (e) {
    document.documentElement.dataset.theme = 'dark';
  }
})();

var BOOTSTRAP_LEADS = [];
var leads = [];
var services = __SERVICES__;
var STATUS_KEY = 'zeplin_lead_statuses_v4';
var OUTREACH_KEY = 'zeplin_outreach_v2';
try {
  ['zeplin_lead_statuses_v1', 'zeplin_lead_statuses_v2',
   'zeplin_lead_statuses_v3', 'zeplin_outreach_v1'].forEach(function (key) {
    localStorage.removeItem(key);
  });
} catch (e) {}
var remoteStatuses = {};
var outreachEvents = [];
var apiReady = false;
