/**
 * CAUKIN prices - Google Sheet menu.
 *
 * Adds "Prices > Refresh prices", which asks GitHub to run the refresh workflow.
 * Needs two Script Properties (Extensions > Apps Script > Project Settings > Script Properties):
 *   GITHUB_TOKEN  fine-grained personal access token with "Contents: Read and write" on the repo
 *   GITHUB_REPO   owner/repo, e.g. caukin/caukinprices
 * The token lives only in Script Properties - never paste it into this code.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Prices')
    .addItem('Refresh prices', 'refreshPrices')
    .addToUi();
}

function refreshPrices() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('GITHUB_TOKEN');
  var repo = props.getProperty('GITHUB_REPO');
  if (!token || !repo) {
    SpreadsheetApp.getUi().alert('Setup needed: add GITHUB_TOKEN and GITHUB_REPO in Apps Script > Project Settings > Script Properties.');
    return;
  }

  var response = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'
    },
    payload: JSON.stringify({ event_type: 'refresh-prices' }),
    muteHttpExceptions: true
  });

  var code = response.getResponseCode();
  if (code === 204) {
    ss.toast('Refresh started, takes ~2 mins. Check Settings > Last run when done.', 'Prices', 10);
  } else if (code === 401 || code === 403 || code === 404) {
    SpreadsheetApp.getUi().alert('GitHub refused the request (HTTP ' + code + '). The token may have expired or lack access to ' + repo + '.');
  } else {
    SpreadsheetApp.getUi().alert('Could not start refresh (HTTP ' + code + '): ' + response.getContentText().slice(0, 200));
  }
}
