// Small helpers for the input form: add/remove rows, load example data.
(function () {
  const body = document.getElementById("rows");
  const template = body.querySelector("tr").cloneNode(true);

  function blankRow() {
    const tr = template.cloneNode(true);
    tr.querySelectorAll("input").forEach((i) => (i.value = ""));
    tr.querySelector("select").value = "revenue";
    return tr;
  }

  function addRow(values) {
    const tr = blankRow();
    if (values) {
      const [cat, type, f, a, fu, au, notes] = values;
      tr.querySelector('[name="category"]').value = cat;
      tr.querySelector('[name="type"]').value = type;
      tr.querySelector('[name="forecast"]').value = f;
      tr.querySelector('[name="actual"]').value = a;
      tr.querySelector('[name="forecast_units"]').value = fu;
      tr.querySelector('[name="actual_units"]').value = au;
      tr.querySelector('[name="notes"]').value = notes;
    }
    body.appendChild(tr);
  }

  body.addEventListener("click", (e) => {
    if (e.target.classList.contains("x")) {
      if (body.rows.length > 1) e.target.closest("tr").remove();
      else blankRowsInPlace();
    }
  });

  function blankRowsInPlace() {
    body.innerHTML = "";
    addRow();
  }

  document.getElementById("add-row").addEventListener("click", () => addRow());
  document.getElementById("clear-rows").addEventListener("click", blankRowsInPlace);

  // A made-up month for a retail business, built to show each type of variance.
  const example = [
    ["Product sales", "revenue", "12000000", "10500000", "40000", "35000", "Store footfall was down in the last two weeks of the month"],
    ["Subscription revenue", "revenue", "3000000", "3150000", "10000", "9500", "Price increase of 10% went live on 1 Oct"],
    ["Services revenue", "revenue", "2000000", "1400000", "", "", "Client A implementation delayed to November, so the invoice moves too"],
    ["Marketing spend", "cost", "1500000", "1950000", "", "", ""],
    ["Salaries", "cost", "5000000", "5050000", "", "", ""],
    ["Logistics", "cost", "800000", "1300000", "", "", "One-off penalty paid to courier partner on contract exit"],
    ["Office rent", "cost", "600000", "600000", "", "", ""],
  ];

  document.getElementById("load-example").addEventListener("click", () => {
    document.querySelector('[name="title"]').value = "October close, retail India";
    document.querySelector('[name="period"]').value = "Oct 2026";
    document.querySelector('[name="currency"]').value = "INR";
    body.innerHTML = "";
    example.forEach((r) => addRow(r));
  });

  document.getElementById("variance-form").addEventListener("submit", () => {
    const btn = document.getElementById("submit-btn");
    btn.disabled = true;
    btn.textContent = "Working it out...";
  });
})();
