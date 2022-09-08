// Requires the following libraries:
// https://cdn.jsdelivr.net/npm/chart.js@^3
// https://cdn.jsdelivr.net/npm/luxon@^3
// https://cdn.jsdelivr.net/npm/chartjs-adapter-luxon@^1
// https://apis.google.com/js/api.js


"use strict";
document.addEventListener("DOMContentLoaded", function () {
  const SPREADSHEET_ID = "1e_qMx2egdqsUFI_46u0JW1daivNzeVteudA5BwY-8oM";
  const SHEET_RANGE = "Sheet1";
  const CHART_DIV = "ucscPrecipitationChart";

  const DISCOVERY_DOC = "https://sheets.googleapis.com/$discovery/rest?version=v4";
  const API_KEY = "AIzaSyBEHWGl1JIg3BAMYQ0ORhlchTjxtA2i_IE";

  const chartDiv = document.getElementById(CHART_DIV);
  if (chartDiv === null) {
    return;
  }

  gapi.load("client", async () => {
    await gapi.client.init({
      apiKey: API_KEY,
      discoveryDocs: [DISCOVERY_DOC],
    });
    initChart(chartDiv);
  });

  function initChart(chartDiv) {
    fetchData(
      data => chartData(chartDiv, data),
      err => reportErr(chartDiv, err),
    );
  }

  function fetchData(okCb, errCb) {
    try {
      gapi.client.sheets.spreadsheets.values.get({
        spreadsheetId: SPREADSHEET_ID,
        range: SHEET_RANGE,
      })
        .then((response) => {
          okCb(response.result.values);
        });
    } catch (err) {
      errCb(err);
    }
  }

  function transpose2d(arr) {
    return arr[0].map((_, c) => arr.map(r => r[c]));
  }

  function reportErr(chartDiv, err) {
    console.log(err);
    chartDiv.innerHTML = '<p style="text-align:center;color:red;">Error encountered while loading precipitation chart :(</p>';
  }

  function chartData(chartDiv, rows) {
    // These colors match the ZENTRA display
    const colors = ["#276c9b", "#54a0d4", "#007d00", "#00b000"];
    const cols = transpose2d(rows);

    let datasets = [];
    for (let i = 0; i < cols.length; i += 2) {
      let data = [];
      for (let j = 1; j < cols[i].length; j++) {
        data.push({
          x: luxon.DateTime.fromSeconds(parseInt(cols[i][j])),
          y: parseFloat(cols[i + 1][j]),
        });
      }

      let dataset = {
        categoryPercentage: 1.0,
        barPercentage: 1.0,
        label: cols[i][0],
        data: data,
      };

      const j = i / 2;
      if (j < colors.length) {
        dataset.backgroundColor = colors[j];
      }

      datasets.push(dataset);
    }

    const canvas = document.createElement("canvas");
    chartDiv.appendChild(canvas);
    const ctx = canvas.getContext("2d");

    const _ = new Chart(ctx, {
      type: "bar",
      data: {
        datasets: datasets,
      },
      options: {
        scales: {
          yAxis: {
            title: {
              display: true,
              text: "Precipitation (mm)",
            },
            ticks: {
              beginAtZero: true
            }
          },
          xAxis: {
            type: "time",
            time: {
              unit: "minute",
              displayFormats: {
                "minute": "MM/dd/yy t",
              },
            },
            ticks: {
              maxTicksLimit: 10,
            }
          }
        }
      }
    });
  }
});