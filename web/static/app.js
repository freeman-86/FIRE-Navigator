"use strict";

// アプリ全体の状態。GET /api/plan の返り値そのもの（local_data_adapter.pyが読み込める形）を
// そのまま保持し、フォームの入力はここへ直接書き込む。POST時もこの形のままそっくり送る。
let state = null;
let assetClasses = {}; // {資産クラスコード: 表示名}
let accountTypes = []; // [口座タイプコード, ...]

const CONDITION_TYPE_LABELS = {
  plan_start: "プラン開始時から",
  age: "年齢で指定",
  date: "年月で指定",
};

function setPath(obj, path, value) {
  const keys = path.split(".");
  let target = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    target = target[keys[i]];
  }
  target[keys[keys.length - 1]] = value;
}

function getPath(obj, path) {
  return path.split(".").reduce((acc, key) => (acc == null ? acc : acc[key]), obj);
}

function escapeHtml(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function optionsHtml(values, selected, labelFn) {
  return values
    .map((value) => {
      const label = labelFn ? labelFn(value) : value;
      const isSelected = value === selected ? " selected" : "";
      return `<option value="${escapeHtml(value)}"${isSelected}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

// --- 発生条件（start_condition/end_condition/trigger）の小さなウィジェット --------------------

function conditionWidgetHtml(pathPrefix, condition, allowNone) {
  const type = condition ? condition.type : "";
  const typeOptions = allowNone
    ? [["", "（条件なし）"], ...Object.entries(CONDITION_TYPE_LABELS)]
    : Object.entries(CONDITION_TYPE_LABELS);
  const options = typeOptions
    .map(([value, label]) => `<option value="${value}"${value === type ? " selected" : ""}>${escapeHtml(label)}</option>`)
    .join("");

  let valueInput = "";
  if (type === "age") {
    valueInput = `<input type="number" class="condition-value" data-condition-field="age" data-path="${pathPrefix}" value="${escapeHtml(condition.age)}" placeholder="年齢">`;
  } else if (type === "date") {
    valueInput = `<input type="month" class="condition-value" data-condition-field="date" data-path="${pathPrefix}" value="${escapeHtml(condition.date ? condition.date.slice(0, 7) : "")}">`;
  }

  return `
    <span class="condition-widget">
      <select class="condition-type" data-path="${pathPrefix}">${options}</select>
      ${valueInput}
    </span>
  `;
}

function readConditionFromWidget(widgetEl) {
  const typeSelect = widgetEl.querySelector(".condition-type");
  const type = typeSelect.value;
  if (!type) return null;
  if (type === "plan_start") return { type: "plan_start" };
  if (type === "age") {
    const ageInput = widgetEl.querySelector('[data-condition-field="age"]');
    return { type: "age", age: ageInput && ageInput.value !== "" ? Number(ageInput.value) : null };
  }
  if (type === "date") {
    const dateInput = widgetEl.querySelector('[data-condition-field="date"]');
    const raw = dateInput ? dateInput.value : "";
    return { type: "date", date: raw ? `${raw}-01` : null };
  }
  return null;
}

// --- 基本設定 -------------------------------------------------------------------------------

function renderSettings() {
  const container = document.getElementById("settings-fields");
  container.innerHTML = `
    <label>プランID<input data-path="plan_id" value="${escapeHtml(state.plan_id)}"></label>
    <label>プラン名<input data-path="name" value="${escapeHtml(state.name)}"></label>
    <label>生年月日<input type="date" data-path="user.birth_date" value="${escapeHtml(state.user.birth_date)}"></label>
    <label>インフレ率（例: 0.02 = 2%）<input data-path="assumptions.inflation_rate" value="${escapeHtml(state.assumptions.inflation_rate)}"></label>
    <label>国民年金見込額（年額）<input type="number" data-path="pension.national_pension_estimate_annual" value="${escapeHtml(state.pension.national_pension_estimate_annual)}"></label>
    <label>厚生年金見込額（年額）<input type="number" data-path="pension.employee_pension_estimate_annual" value="${escapeHtml(state.pension.employee_pension_estimate_annual)}"></label>
    <label>年金受給開始年齢<input type="number" data-path="pension.claim_age" value="${escapeHtml(state.pension.claim_age)}"></label>
    <label>想定寿命<input type="number" data-path="life_expectancy_age" value="${escapeHtml(state.life_expectancy_age)}"></label>
    <label>目標資産（想定寿命時点）<input type="number" data-path="target_ending_networth" value="${escapeHtml(state.target_ending_networth)}"></label>
  `;
  container.querySelectorAll("[data-path]").forEach((inputEl) => {
    inputEl.addEventListener("input", () => setPath(state, inputEl.dataset.path, inputEl.value));
  });
}

// --- 口座 -----------------------------------------------------------------------------------

function renderAccounts() {
  const container = document.getElementById("accounts-list");
  container.innerHTML = state.accounts
    .map(
      (account, index) => `
      <div class="row" data-index="${index}">
        <button type="button" class="remove-row-btn" data-remove-account="${index}">×</button>
        <label>口座ID<input data-field="account_id" value="${escapeHtml(account.account_id)}"></label>
        <label>口座タイプ<select data-field="account_type">${optionsHtml(accountTypes, account.account_type)}</select></label>
        <label>月次拠出額<input type="number" data-field="monthly_contribution" value="${escapeHtml(account.monthly_contribution)}"></label>
        <label>資産クラス<select data-field="asset_class">${optionsHtml(Object.keys(assetClasses), account.asset_class, (code) => assetClasses[code] || code)}</select></label>
        <label>期待リターン（例: 0.05 = 5%）<input data-field="expected_return" value="${escapeHtml(account.expected_return)}"></label>
        <label>残高<input type="number" data-field="current_value" value="${escapeHtml(account.current_value)}"></label>
        <label>取得原価（空欄=残高と同額）<input type="number" data-field="cost_basis" value="${escapeHtml(account.cost_basis)}"></label>
      </div>
    `
    )
    .join("");

  container.querySelectorAll(".row").forEach((rowEl) => {
    const index = Number(rowEl.dataset.index);
    rowEl.querySelectorAll("[data-field]").forEach((fieldEl) => {
      fieldEl.addEventListener("input", () => {
        state.accounts[index][fieldEl.dataset.field] = fieldEl.value;
      });
    });
  });
  container.querySelectorAll("[data-remove-account]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.accounts.splice(Number(btn.dataset.removeAccount), 1);
      renderAccounts();
    });
  });
}

// --- 収入 -----------------------------------------------------------------------------------

function renderIncomes() {
  const container = document.getElementById("incomes-list");
  container.innerHTML = state.incomes
    .map(
      (income, index) => `
      <div class="row" data-index="${index}">
        <button type="button" class="remove-row-btn" data-remove-income="${index}">×</button>
        <label>収入ID<input data-field="income_id" value="${escapeHtml(income.income_id)}"></label>
        <label>収入源<input data-field="source" value="${escapeHtml(income.source)}"></label>
        <label>年間金額<input type="number" data-field="amount" value="${escapeHtml(income.amount)}"></label>
        <label>成長率（空欄=インフレ率）<input data-field="growth_rate" value="${escapeHtml(income.growth_rate)}"></label>
        <label>開始条件（必須）${conditionWidgetHtml(`incomes[${index}].start_condition`, income.start_condition, false)}</label>
        <label>終了条件（任意）${conditionWidgetHtml(`incomes[${index}].end_condition`, income.end_condition, true)}</label>
      </div>
    `
    )
    .join("");

  bindIncomeRows(container);
}

function bindIncomeRows(container) {
  container.querySelectorAll(".row").forEach((rowEl) => {
    const index = Number(rowEl.dataset.index);
    rowEl.querySelectorAll("[data-field]").forEach((fieldEl) => {
      fieldEl.addEventListener("input", () => {
        state.incomes[index][fieldEl.dataset.field] = fieldEl.value;
      });
    });
    bindConditionWidget(rowEl, `incomes[${index}].start_condition`, (value) => {
      state.incomes[index].start_condition = value;
    });
    bindConditionWidget(rowEl, `incomes[${index}].end_condition`, (value) => {
      state.incomes[index].end_condition = value;
    });
  });
  container.querySelectorAll("[data-remove-income]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.incomes.splice(Number(btn.dataset.removeIncome), 1);
      renderIncomes();
    });
  });
}

function bindConditionWidget(rowEl, pathPrefix, onChange) {
  const widget = rowEl.querySelector(`[data-path="${pathPrefix}"]`)?.closest(".condition-widget");
  if (!widget) return;
  const rerenderAndApply = () => {
    onChange(readConditionFromWidget(widget));
  };
  widget.querySelectorAll("select, input").forEach((el) => el.addEventListener("input", rerenderAndApply));
  // 条件タイプを切り替えたときは、年齢/年月入力欄の表示切り替えが必要なため再描画する。
  const typeSelect = widget.querySelector(".condition-type");
  typeSelect.addEventListener("change", () => {
    onChange(readConditionFromWidget(widget));
    renderAll();
  });
}

// --- 支出（経常・単発） -----------------------------------------------------------------------

function renderExpenses() {
  const container = document.getElementById("expenses-list");
  container.innerHTML = state.expenses
    .map((expense, index) => {
      const isOneTime = expense.kind === "one_time";
      const kindSpecificHtml = isOneTime
        ? `<label>発生条件（必須）${conditionWidgetHtml(`expenses[${index}].trigger`, expense.trigger, false)}</label>`
        : `
          <label>成長率（空欄=インフレ率）<input data-field="growth_rate" value="${escapeHtml(expense.growth_rate)}"></label>
          <label>開始条件（任意）${conditionWidgetHtml(`expenses[${index}].start_condition`, expense.start_condition, true)}</label>
          <label>終了条件（任意）${conditionWidgetHtml(`expenses[${index}].end_condition`, expense.end_condition, true)}</label>
        `;
      return `
      <div class="row" data-index="${index}">
        <button type="button" class="remove-row-btn" data-remove-expense="${index}">×</button>
        <label>支出ID<input data-field="expense_id" value="${escapeHtml(expense.expense_id)}"></label>
        <label>カテゴリ<input data-field="category" value="${escapeHtml(expense.category)}"></label>
        <label>種別
          <select data-field="kind">
            <option value="recurring"${!isOneTime ? " selected" : ""}>経常支出</option>
            <option value="one_time"${isOneTime ? " selected" : ""}>単発支出</option>
          </select>
        </label>
        <label>金額（${isOneTime ? "単発" : "年額"}）<input type="number" data-field="amount" value="${escapeHtml(expense.amount)}"></label>
        ${kindSpecificHtml}
      </div>
    `;
    })
    .join("");

  bindExpenseRows(container);
}

function bindExpenseRows(container) {
  container.querySelectorAll(".row").forEach((rowEl) => {
    const index = Number(rowEl.dataset.index);
    rowEl.querySelectorAll("[data-field]").forEach((fieldEl) => {
      fieldEl.addEventListener("input", () => {
        state.expenses[index][fieldEl.dataset.field] = fieldEl.value;
      });
    });
    const kindSelect = rowEl.querySelector('[data-field="kind"]');
    kindSelect.addEventListener("change", () => {
      // 種別を切り替えたら、その種別で使わないフィールドは送らないよう作り直す
      // （local_data_adapterはkindに合わない項目をSchemaValidationErrorで拒否するため）。
      const id = state.expenses[index];
      if (kindSelect.value === "one_time") {
        state.expenses[index] = {
          expense_id: id.expense_id,
          category: id.category,
          kind: "one_time",
          amount: id.amount,
          trigger: null,
        };
      } else {
        state.expenses[index] = {
          expense_id: id.expense_id,
          category: id.category,
          kind: "recurring",
          amount: id.amount,
          growth_rate: null,
          start_condition: null,
          end_condition: null,
        };
      }
      renderExpenses();
    });
    bindConditionWidget(rowEl, `expenses[${index}].trigger`, (value) => {
      state.expenses[index].trigger = value;
    });
    bindConditionWidget(rowEl, `expenses[${index}].start_condition`, (value) => {
      state.expenses[index].start_condition = value;
    });
    bindConditionWidget(rowEl, `expenses[${index}].end_condition`, (value) => {
      state.expenses[index].end_condition = value;
    });
  });
  container.querySelectorAll("[data-remove-expense]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.expenses.splice(Number(btn.dataset.removeExpense), 1);
      renderExpenses();
    });
  });
}

// --- 配分方針 --------------------------------------------------------------------------------

function renderAllocationPolicy() {
  const container = document.getElementById("allocation-policy-list");
  const targets = state.allocation_policy ? state.allocation_policy.targets : [];
  container.innerHTML = targets
    .map((target, index) => {
      const weightInputs = Object.keys(assetClasses)
        .map((code) => {
          const value = target.weights[code] != null ? target.weights[code] : "";
          return `<label>${escapeHtml(assetClasses[code] || code)}<input type="text" data-weight="${code}" value="${escapeHtml(value)}" placeholder="0.0"></label>`;
        })
        .join("");
      return `
      <div class="row" data-index="${index}">
        <button type="button" class="remove-row-btn" data-remove-target="${index}">×</button>
        <label>この年齢から<input type="number" data-field="age" value="${escapeHtml(target.age)}"></label>
        <div class="weights-grid">${weightInputs}</div>
      </div>
    `;
    })
    .join("");

  container.querySelectorAll(".row").forEach((rowEl) => {
    const index = Number(rowEl.dataset.index);
    const ageInput = rowEl.querySelector('[data-field="age"]');
    ageInput.addEventListener("input", () => {
      state.allocation_policy.targets[index].age = ageInput.value;
    });
    rowEl.querySelectorAll("[data-weight]").forEach((weightInput) => {
      weightInput.addEventListener("input", () => {
        const code = weightInput.dataset.weight;
        if (weightInput.value === "") {
          delete state.allocation_policy.targets[index].weights[code];
        } else {
          state.allocation_policy.targets[index].weights[code] = weightInput.value;
        }
      });
    });
  });
  container.querySelectorAll("[data-remove-target]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.allocation_policy.targets.splice(Number(btn.dataset.removeTarget), 1);
      renderAllocationPolicy();
    });
  });
}

// --- 子供・教育費 ----------------------------------------------------------------------------

function renderChildren() {
  const container = document.getElementById("children-list");
  container.innerHTML = state.children
    .map(
      (child, index) => `
      <div class="row" data-index="${index}">
        <button type="button" class="remove-row-btn" data-remove-child="${index}">×</button>
        <label>子供ID<input data-field="child_id" value="${escapeHtml(child.child_id)}"></label>
        <label>生年月日<input type="date" data-field="birth_date" value="${escapeHtml(child.birth_date)}"></label>
      </div>
    `
    )
    .join("");

  container.querySelectorAll(".row").forEach((rowEl) => {
    const index = Number(rowEl.dataset.index);
    rowEl.querySelectorAll("[data-field]").forEach((fieldEl) => {
      fieldEl.addEventListener("input", () => {
        state.children[index][fieldEl.dataset.field] = fieldEl.value;
      });
    });
  });
  container.querySelectorAll("[data-remove-child]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.children.splice(Number(btn.dataset.removeChild), 1);
      renderChildren();
      renderEducationExpenses();
    });
  });
}

function renderEducationExpenses() {
  const container = document.getElementById("education-expenses-list");
  const childIds = state.children.map((c) => c.child_id);
  container.innerHTML = state.education_expenses
    .map(
      (band, index) => `
      <div class="row" data-index="${index}">
        <button type="button" class="remove-row-btn" data-remove-band="${index}">×</button>
        <label>教育費ID<input data-field="band_id" value="${escapeHtml(band.band_id)}"></label>
        <label>子供<select data-field="child_id">${optionsHtml(childIds, band.child_id)}</select></label>
        <label>カテゴリ<input data-field="category" value="${escapeHtml(band.category)}"></label>
        <label>開始年齢<input type="number" data-field="start_age" value="${escapeHtml(band.start_age)}"></label>
        <label>終了年齢<input type="number" data-field="end_age" value="${escapeHtml(band.end_age)}"></label>
        <label>月額<input type="number" data-field="monthly_amount" value="${escapeHtml(band.monthly_amount)}"></label>
      </div>
    `
    )
    .join("");

  container.querySelectorAll(".row").forEach((rowEl) => {
    const index = Number(rowEl.dataset.index);
    rowEl.querySelectorAll("[data-field]").forEach((fieldEl) => {
      fieldEl.addEventListener("input", () => {
        state.education_expenses[index][fieldEl.dataset.field] = fieldEl.value;
      });
    });
  });
  container.querySelectorAll("[data-remove-band]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.education_expenses.splice(Number(btn.dataset.removeBand), 1);
      renderEducationExpenses();
    });
  });
}

// --- 全体の描画・追加ボタン --------------------------------------------------------------------

function renderAll() {
  renderSettings();
  renderAccounts();
  renderIncomes();
  renderExpenses();
  renderAllocationPolicy();
  renderChildren();
  renderEducationExpenses();
}

function setupAddButtons() {
  document.getElementById("add-account-btn").addEventListener("click", () => {
    state.accounts.push({
      account_id: "",
      account_type: accountTypes[0] || "",
      monthly_contribution: null,
      asset_class: Object.keys(assetClasses)[0] || "",
      expected_return: "",
      current_value: null,
      cost_basis: null,
    });
    renderAccounts();
  });

  document.getElementById("add-income-btn").addEventListener("click", () => {
    state.incomes.push({
      income_id: "",
      source: "",
      amount: null,
      growth_rate: null,
      start_condition: { type: "plan_start" },
      end_condition: null,
    });
    renderIncomes();
  });

  document.getElementById("add-expense-btn").addEventListener("click", () => {
    state.expenses.push({
      expense_id: "",
      category: "",
      kind: "recurring",
      amount: null,
      growth_rate: null,
      start_condition: null,
      end_condition: null,
    });
    renderExpenses();
  });

  document.getElementById("add-allocation-target-btn").addEventListener("click", () => {
    if (!state.allocation_policy) {
      state.allocation_policy = { targets: [] };
    }
    state.allocation_policy.targets.push({ age: null, weights: {} });
    renderAllocationPolicy();
  });

  document.getElementById("add-child-btn").addEventListener("click", () => {
    state.children.push({ child_id: "", birth_date: "" });
    renderChildren();
  });

  document.getElementById("add-education-expense-btn").addEventListener("click", () => {
    state.education_expenses.push({
      band_id: "",
      child_id: state.children[0] ? state.children[0].child_id : "",
      category: "",
      start_age: null,
      end_age: null,
      monthly_amount: null,
    });
    renderEducationExpenses();
  });
}

// --- 実行ボタン・結果表示 ----------------------------------------------------------------------

function buildPayload() {
  // ""（未入力）はnull（未設定）として送る。local_data_adapter側は空文字/nullを同じ扱いにするが、
  // 数値フィールドに空文字が残ってJSON上の型が揺れるのを避けるため、送信直前にここでnull化する。
  return JSON.parse(JSON.stringify(state), (_key, value) => (value === "" ? null : value));
}

async function runSimulation() {
  const runBtn = document.getElementById("run-btn");
  const statusEl = document.getElementById("run-status");
  runBtn.disabled = true;
  statusEl.innerHTML = '<p class="status-running">実行中...（数秒で完了します）</p>';

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    const body = await response.json();

    if (!response.ok) {
      statusEl.innerHTML =
        '<p class="status-error">入力内容にエラーがあります:</p><ul>' +
        body.errors.map((e) => `<li><code>${escapeHtml(e.field_path)}</code>: ${escapeHtml(e.message)}</li>`).join("") +
        "</ul>";
      return;
    }

    statusEl.innerHTML = '<p class="status-ok">計算が完了しました。</p>';
    renderResults(body);
  } catch (err) {
    statusEl.innerHTML = `<p class="status-error">通信エラーが発生しました: ${escapeHtml(String(err))}</p>`;
  } finally {
    runBtn.disabled = false;
  }
}

function yen(amount) {
  if (amount == null) return "-";
  return `${Number(amount).toLocaleString("ja-JP")}円`;
}

function renderResults(output) {
  document.getElementById("results-empty").hidden = true;
  const content = document.getElementById("results-content");
  content.hidden = false;

  const d = output.dashboard;
  document.getElementById("kpi-cards").innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card"><div class="kpi-label">現在の純資産</div><div class="kpi-value">${yen(d.current_networth)}</div></div>
      <div class="kpi-card"><div class="kpi-label">追加で使える金額/月</div><div class="kpi-value">${yen(d.extra_monthly_budget)}</div></div>
      <div class="kpi-card"><div class="kpi-label">資産枯渇年齢</div><div class="kpi-value">${d.depletion_age != null ? d.depletion_age + "歳" : "枯渇なし"}</div></div>
      <div class="kpi-card"><div class="kpi-label">目標資産との差</div><div class="kpi-value">${yen(d.surplus_vs_target)}</div></div>
    </div>
  `;

  const chart = output.charts.networth_chart;
  if (chart) {
    const rows = chart.x
      .map((year, i) => {
        const total = chart.series.reduce((sum, series) => sum + (series.values[i] || 0), 0);
        return `<tr><td>${year}</td><td>${yen(total)}</td></tr>`;
      })
      .join("");
    document.getElementById("networth-table").innerHTML = `
      <table><thead><tr><th>西暦年</th><th>純資産</th></tr></thead><tbody>${rows}</tbody></table>
    `;
  }

  const table = output.tables.sensitivity_table;
  if (table) {
    const header = `<tr><th></th>${table.column_labels.map((l) => `<th>${escapeHtml(l)}</th>`).join("")}</tr>`;
    const rows = table.row_labels
      .map(
        (label, r) =>
          `<tr><th>${escapeHtml(label)}</th>${table.cells[r].map((v) => `<td>${yen(v)}</td>`).join("")}</tr>`
      )
      .join("");
    document.getElementById("sensitivity-table").innerHTML = `<table><thead>${header}</thead><tbody>${rows}</tbody></table>`;
  }
}

// --- 初期化 ---------------------------------------------------------------------------------

async function init() {
  const [planResponse, assetClassesResponse, accountTypesResponse] = await Promise.all([
    fetch("/api/plan"),
    fetch("/api/asset-classes"),
    fetch("/api/account-types"),
  ]);
  state = await planResponse.json();
  assetClasses = await assetClassesResponse.json();
  accountTypes = await accountTypesResponse.json();

  // 既存データに合わせて、配列であるべきフィールドの欠落を補う（初回起動時の空プラン等）。
  state.accounts = state.accounts || [];
  state.incomes = state.incomes || [];
  state.expenses = state.expenses || [];
  state.children = state.children || [];
  state.education_expenses = state.education_expenses || [];

  renderAll();
  setupAddButtons();
  document.getElementById("run-btn").addEventListener("click", runSimulation);
}

init();
