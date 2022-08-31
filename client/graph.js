document.addEventListener("DOMContentLoaded", function() {
  const SPREADSHEET_ID = "1e_qMx2egdqsUFI_46u0JW1daivNzeVteudA5BwY-8oM";

  const graphDiv = document.getElementById("ucscPrecipitationGraph");
  if (graphDiv === null) {
    return;
  }

  const canv = document.createElement("canvas");
  graphDiv.appendChild(canv);
  const ctx = canv.getContext("2d");

  function getData(okCallback, errCallback) {
    try {
      gapi.client.sheets.spreadsheets.values.get({
        spreadsheetId: SPREADSHEET_ID,
        range: "",
      })
      .then((response) => {
        okCallback(response.values);
      });
    } catch (err) {
      errCallback(err);
      return;
    }
  }

  function drawGraph(values) {

  }

  function reportErr(err) {

  }

  getData(drawGraph, reportErr);
});