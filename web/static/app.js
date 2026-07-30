"use strict";

// アプリ全体の状態。GET /api/plan の返り値そのもの（local_data_adapter.pyが読み込める形）を
// そのまま保持し、フォームの入力はここへ直接書き込む。POST時もこの形のままそっくり送る。
// 金額(money)・割合(percent)フィールドは、state上は常に生の値（"1000000"・"0.05"）を保ち、
// 表示用のコンマ区切り／％変換はレンダリング・入力バインド側だけで行う。
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

// --- 金額・割合フィールドの表示整形／入力パース -------------------------------------------------

function formatMoneyForDisplay(value) {
  if (value === null || value === undefined || value === "") return "";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString("ja-JP");
}

function parseMoneyFromInput(raw) {
  const cleaned = raw.replace(/,/g, "").trim();
  return cleaned === "" ? null : cleaned;
}

// state上は生の小数（0.05）で持ち、表示だけ%に変換する（例: 0.05 -> "5"）。
function formatPercentForDisplay(rateValue) {
  if (rateValue === null || rateValue === undefined || rateValue === "") return "";
  const num = Number(rateValue) * 100;
  if (Number.isNaN(num)) return String(rateValue);
  // 浮動小数点の誤差(4.999999999999999等)を避けるため丸めてから文字列化する
  return String(Math.round(num * 1e10) / 1e10);
}

function parsePercentFromInput(raw) {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const num = Number(trimmed);
  if (Number.isNaN(num)) return trimmed; // 数値でなければそのまま渡し、バックエンドの検証に委ねる
  return String(num / 100);
}

// data-format="money"|"percent"|未指定 に応じて、フォーカス時は生の値で編集しやすくし、
// blur時にコンマ/％表示へ整形し直す。getValue/setValueで対象（stateの該当フィールド）を読み書きする。
function bindFormattedField(el, getValue, setValue, format) {
  if (format === "money") {
    el.addEventListener("focus", () => {
      const v = getValue();
      el.value = v === null || v === undefined ? "" : String(v).replace(/,/g, "");
    });
    el.addEventListener("input", () => setValue(parseMoneyFromInput(el.value)));
    el.addEventListener("blur", () => {
      el.value = formatMoneyForDisplay(getValue());
    });
  } else if (format === "percent") {
    el.addEventListener("input", () => setValue(parsePercentFromInput(el.value)));
  } else {
    el.addEventListener("input", () => setValue(el.value));
  }
}

// data-field方式（行データ: target[field]）の入力欄を一括でバインドする。
function bindDataFields(scopeEl, target) {
  scopeEl.querySelectorAll("[data-field]").forEach((el) => {
    const field = el.dataset.field;
    bindFormattedField(el, () => target[field], (value) => { target[field] = value; }, el.dataset.format);
  });
}

function moneyFieldHtml(label, dataField, value) {
  return `<label>${label}<input type="text" inputmode="numeric" data-field="${dataField}" data-format="money" value="${escapeHtml(formatMoneyForDisplay(value))}"></label>`;
}

function percentFieldHtml(label, dataField, value) {
  return `
    <label>${label}
      <span class="suffix-group">
        <input type="text" inputmode="decimal" data-field="${dataField}" data-format="percent" value="${escapeHtml(formatPercentForDisplay(value))}">
        <span class="suffix">%</span>
      </span>
    </label>
  `;
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
    ${percentFieldHtmlPath("インフレ率", "assumptions.inflation_rate", state.assumptions.inflation_rate)}
    ${moneyFieldHtmlPath("国民年金見込額（年額）", "pension.national_pension_estimate_annual", state.pension.national_pension_estimate_annual)}
    ${moneyFieldHtmlPath("厚生年金見込額（年額）", "pension.employee_pension_estimate_annual", state.pension.employee_pension_estimate_annual)}
    <label>年金受給開始年齢<input type="number" data-path="pension.claim_age" value="${escapeHtml(state.pension.claim_age)}"></label>
    <label>想定寿命<input type="number" data-path="life_expectancy_age" value="${escapeHtml(state.life_expectancy_age)}"></label>
    ${moneyFieldHtmlPath("目標資産（想定寿命時点）", "target_ending_networth", state.target_ending_networth)}
  `;
  container.querySelectorAll("[data-path]").forEach((inputEl) => {
    const path = inputEl.dataset.path;
    bindFormattedField(
      inputEl,
      () => getPath(state, path),
      (value) => setPath(state, path, value),
      inputEl.dataset.format
    );
  });
}

function moneyFieldHtmlPath(label, path, value) {
  return `<label>${label}<input type="text" inputmode="numeric" data-path="${path}" data-format="money" value="${escapeHtml(formatMoneyForDisplay(value))}"></label>`;
}

function percentFieldHtmlPath(label, path, value) {
  return `
    <label>${label}
      <span class="suffix-group">
        <input type="text" inputmode="decimal" data-path="${path}" data-format="percent" value="${escapeHtml(formatPercentForDisplay(value))}">
        <span class="suffix">%</span>
      </span>
    </label>
  `;
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
        ${moneyFieldHtml("月次拠出額", "monthly_contribution", account.monthly_contribution)}
        <label>資産クラス<select data-field="asset_class">${optionsHtml(Object.keys(assetClasses), account.asset_class, (code) => assetClasses[code] || code)}</select></label>
        ${percentFieldHtml("期待リターン", "expected_return", account.expected_return)}
        ${moneyFieldHtml("残高", "current_value", account.current_value)}
        ${moneyFieldHtml("取得原価（空欄=残高と同額）", "cost_basis", account.cost_basis)}
      </div>
    `
    )
    .join("");

  container.querySelectorAll(".row").forEach((rowEl) => {
    const index = Number(rowEl.dataset.index);
    bindDataFields(rowEl, state.accounts[index]);
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
        ${moneyFieldHtml("年間金額", "amount", income.amount)}
        ${percentFieldHtml("成長率（空欄=インフレ率）", "growth_rate", income.growth_rate)}
        <label class="wide">開始条件（必須）${conditionWidgetHtml(`incomes[${index}].start_condition`, income.start_condition, false)}</label>
        <label class="wide">終了条件（任意）${conditionWidgetHtml(`incomes[${index}].end_condition`, income.end_condition, true)}</label>
      </div>
    `
    )
    .join("");

  bindIncomeRows(container);
}

function bindIncomeRows(container) {
  container.querySelectorAll(".row").forEach((rowEl) => {
    const index = Number(rowEl.dataset.index);
    bindDataFields(rowEl, state.incomes[index]);
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
        ? `<label class="wide">発生条件（必須）${conditionWidgetHtml(`expenses[${index}].trigger`, expense.trigger, false)}</label>`
        : `
          ${percentFieldHtml("成長率（空欄=インフレ率）", "growth_rate", expense.growth_rate)}
          <label class="wide">開始条件（任意）${conditionWidgetHtml(`expenses[${index}].start_condition`, expense.start_condition, true)}</label>
          <label class="wide">終了条件（任意）${conditionWidgetHtml(`expenses[${index}].end_condition`, expense.end_condition, true)}</label>
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
        ${moneyFieldHtml(`金額（${isOneTime ? "単発" : "年額"}）`, "amount", expense.amount)}
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
    bindDataFields(rowEl, state.expenses[index]);
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
          return `
            <label>${escapeHtml(assetClasses[code] || code)}
              <span class="suffix-group">
                <input type="text" inputmode="decimal" data-weight="${code}" value="${escapeHtml(formatPercentForDisplay(value))}" placeholder="0">
                <span class="suffix">%</span>
              </span>
            </label>
          `;
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
        const parsed = parsePercentFromInput(weightInput.value);
        if (parsed === null) {
          delete state.allocation_policy.targets[index].weights[code];
        } else {
          state.allocation_policy.targets[index].weights[code] = parsed;
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
    bindDataFields(rowEl, state.children[index]);
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
        ${moneyFieldHtml("月額", "monthly_amount", band.monthly_amount)}
      </div>
    `
    )
    .join("");

  container.querySelectorAll(".row").forEach((rowEl) => {
    const index = Number(rowEl.dataset.index);
    bindDataFields(rowEl, state.education_expenses[index]);
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
  const includeMontecarlo = document.getElementById("include-montecarlo-checkbox").checked;
  runBtn.disabled = true;
  statusEl.innerHTML = includeMontecarlo
    ? '<p class="status-running">実行中...（モンテカルロ/ヒストリカルを含むため数十秒〜数分かかります）</p>'
    : '<p class="status-running">実行中...（数秒で完了します）</p>';

  try {
    const url = includeMontecarlo ? "/api/run?include_montecarlo=1" : "/api/run";
    const response = await fetch(url, {
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

function pctText(rateValue) {
  if (rateValue == null) return "-";
  return `${(Number(rateValue) * 100).toLocaleString("ja-JP", { maximumFractionDigits: 2 })}%`;
}

// --- 色ユーティリティ（dataviz skillの参照パレット。CSS変数から実際の値を読む） -----------------

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function seriesColors() {
  return [1, 2, 3, 4, 5, 6, 7, 8].map((i) => cssVar(`--series-${i}`));
}

function hexToRgb(hex) {
  const clean = hex.replace("#", "");
  const num = parseInt(clean, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
}

function hexToRgba(hex, alpha) {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function mixColor(hexA, hexB, t) {
  const a = hexToRgb(hexA);
  const b = hexToRgb(hexB);
  const mixed = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${mixed[0]}, ${mixed[1]}, ${mixed[2]})`;
}

// --- KPIカード（stat tile。色だけに頼らずアイコン＋文言でも状態を示す） --------------------------

function kpiDeltaHtml(status, text) {
  const icon = { good: "✓", critical: "✗", neutral: "–" }[status];
  return `<div class="kpi-delta status-${status}"><span aria-hidden="true">${icon}</span><span>${escapeHtml(text)}</span></div>`;
}

function renderKpiCards(dashboard) {
  const depletionDelta =
    dashboard.depletion_age == null
      ? kpiDeltaHtml("good", "想定寿命まで枯渇しない見込み")
      : kpiDeltaHtml("critical", "想定寿命より前に枯渇する見込み");
  const surplusDelta =
    dashboard.surplus_vs_target >= 0
      ? kpiDeltaHtml("good", "目標資産を達成する見込み")
      : kpiDeltaHtml("critical", "目標資産に届かない見込み");

  document.getElementById("kpi-cards").innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">現在の純資産</div>
        <div class="kpi-value">${yen(dashboard.current_networth)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">追加で使える金額/月</div>
        <div class="kpi-value">${yen(dashboard.extra_monthly_budget)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">資産枯渇年齢</div>
        <div class="kpi-value">${dashboard.depletion_age != null ? dashboard.depletion_age + "歳" : "枯渇なし"}</div>
        ${depletionDelta}
      </div>
      <div class="kpi-card">
        <div class="kpi-label">目標資産との差</div>
        <div class="kpi-value">${yen(dashboard.surplus_vs_target)}</div>
        ${surplusDelta}
      </div>
    </div>
  `;
}

// --- 純資産推移（積み上げ面グラフ） -------------------------------------------------------------

let networthChartInstance = null;

function commonChartOptions() {
  const textColor = cssVar("--text-secondary");
  const gridColor = cssVar("--chart-grid");
  const axisColor = cssVar("--chart-axis");
  return {
    responsive: true,
    // 親要素（.chart-canvas-wrap、CSSで高さ固定）いっぱいに描画する。falseにしないと、
    // 幅の広い結果パネルに対してアスペクト比を保とうとして縦に間延びしてしまう。
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "bottom", labels: { color: textColor, boxWidth: 12, boxHeight: 12 } },
      tooltip: {
        callbacks: {
          label: (ctx) => `${ctx.dataset.label}: ${yen(ctx.parsed.y)}`,
        },
      },
    },
    scales: {
      x: { ticks: { color: textColor }, grid: { color: gridColor }, border: { color: axisColor } },
      y: {
        ticks: { color: textColor, callback: (v) => yen(v) },
        grid: { color: gridColor },
        border: { color: axisColor },
      },
    },
  };
}

function renderNetworthChart(chart) {
  if (networthChartInstance) {
    networthChartInstance.destroy();
  }
  const colors = seriesColors();
  const datasets = chart.series.map((series, index) => {
    const color = colors[index % colors.length];
    return {
      label: series.name,
      data: series.values,
      borderColor: color,
      backgroundColor: hexToRgba(color, 0.55),
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
      tension: 0,
    };
  });

  const options = commonChartOptions();
  options.scales.y.stacked = true;
  options.scales.x.stacked = true;

  networthChartInstance = new Chart(document.getElementById("networth-chart"), {
    type: "line",
    data: { labels: chart.x, datasets },
    options,
  });

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

// --- モンテカルロ／ヒストリカル（p10-p90帯＋中央値） ----------------------------------------------

let montecarloChartInstance = null;
let historicalChartInstance = null;

function renderPercentileChart(canvasEl, existingInstance, chartData, colorHex) {
  if (existingInstance) {
    existingInstance.destroy();
  }
  const options = commonChartOptions();

  return new Chart(canvasEl, {
    type: "line",
    data: {
      labels: chartData.x,
      datasets: [
        {
          // 下位10%: 細めの破線・低い不透明度（弱気シナリオが視覚的にも控えめになるよう）
          label: "下位10%",
          data: chartData.p10,
          borderColor: hexToRgba(colorHex, 0.5),
          borderWidth: 1.25,
          borderDash: [2, 3],
          pointRadius: 0,
          fill: false,
          tension: 0,
        },
        {
          // 上位10%: 太めの破線・高い不透明度で、下位10%とは間隔・濃さの両方で見分けがつくようにする
          label: "上位10%",
          data: chartData.p90,
          borderColor: hexToRgba(colorHex, 0.9),
          borderWidth: 1.75,
          borderDash: [9, 3],
          backgroundColor: hexToRgba(colorHex, 0.15),
          pointRadius: 0,
          fill: "-1",
          tension: 0,
        },
        {
          label: "中央値",
          data: chartData.p50,
          borderColor: colorHex,
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
          tension: 0,
        },
      ],
    },
    options,
  });
}

function percentileChartTableHtml(chartData) {
  const rows = chartData.x
    .map(
      (year, i) =>
        `<tr><td>${year}</td><td>${yen(chartData.p10[i])}</td><td>${yen(chartData.p50[i])}</td><td>${yen(chartData.p90[i])}</td></tr>`
    )
    .join("");
  return `
    <table>
      <thead><tr><th>西暦年</th><th>下位10%</th><th>中央値</th><th>上位10%</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderMontecarloSection(output) {
  const section = document.getElementById("montecarlo-section");
  const montecarloCard = document.getElementById("montecarlo-chart-card");
  const historicalCard = document.getElementById("historical-chart-card");
  const montecarloChart = output.charts.montecarlo_distribution_chart;
  const historicalChart = output.charts.historical_distribution_chart;

  const hasAny = Boolean(montecarloChart || historicalChart);
  section.hidden = !hasAny;
  if (!hasAny) return;

  const colors = seriesColors();

  montecarloCard.hidden = !montecarloChart;
  if (montecarloChart) {
    montecarloChartInstance = renderPercentileChart(
      document.getElementById("montecarlo-chart"),
      montecarloChartInstance,
      montecarloChart,
      colors[0]
    );
    const rate = output.summary.montecarlo_success_rate;
    montecarloCard.querySelector("figcaption").textContent =
      rate != null ? `モンテカルロ（成功確率 ${(rate * 100).toFixed(1)}%）` : "モンテカルロ";
    document.getElementById("montecarlo-table").innerHTML = percentileChartTableHtml(montecarloChart);
  }

  historicalCard.hidden = !historicalChart;
  if (historicalChart) {
    historicalChartInstance = renderPercentileChart(
      document.getElementById("historical-chart"),
      historicalChartInstance,
      historicalChart,
      colors[1]
    );
    const rate = output.summary.historical_success_rate;
    historicalCard.querySelector("figcaption").textContent =
      rate != null ? `ヒストリカル（成功確率 ${(rate * 100).toFixed(1)}%）` : "ヒストリカル";
    document.getElementById("historical-table").innerHTML = percentileChartTableHtml(historicalChart);
  }
}

// --- 感応度分析（中央値からの乖離を青(良化)/赤(悪化)のダイバージングカラーで示す） -------------------

function renderSensitivityTable(table) {
  if (!table) {
    document.getElementById("sensitivity-table").innerHTML = "";
    return;
  }

  const flatValues = table.cells.flat();
  const sorted = [...flatValues].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const maxDeviation = Math.max(...flatValues.map((v) => Math.abs(v - median)), 1);

  const posColor = cssVar("--div-pos");
  const negColor = cssVar("--div-neg");
  const midColor = cssVar("--div-mid");
  const textColor = cssVar("--text-primary");

  const header = `<tr><th></th>${table.column_labels.map((l) => `<th>${escapeHtml(l)}</th>`).join("")}</tr>`;
  const rows = table.row_labels
    .map((label, r) => {
      const cells = table.cells[r]
        .map((value) => {
          const t = Math.max(-1, Math.min(1, (value - median) / maxDeviation)) * 0.6;
          const bg = t >= 0 ? mixColor(midColor, posColor, t) : mixColor(midColor, negColor, -t);
          return `<td style="background:${bg};color:${textColor}">${yen(value)}</td>`;
        })
        .join("");
      return `<tr><th>${escapeHtml(label)}</th>${cells}</tr>`;
    })
    .join("");

  document.getElementById("sensitivity-table").innerHTML = `<table><thead>${header}</thead><tbody>${rows}</tbody></table>`;
}

// --- 月次詳細（旧Sheets版の出力_月次詳細に相当。取り崩し不足額が出ている月を強調する） -------------

function renderMonthlyDetailTable(monthly) {
  const section = document.getElementById("monthly-detail-section");
  if (!monthly) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const shortfallIndex = monthly.shortfall_column_index;
  const header = `<tr>${monthly.column_labels.map((label) => `<th>${escapeHtml(label)}</th>`).join("")}</tr>`;
  const rows = monthly.rows
    .map((row) => {
      const hasShortfall = row[shortfallIndex] > 0;
      // 先頭3列（西暦年・月・年齢）はそのままの数値、それ以外は円表示にする
      const cells = row.map((value, i) => `<td>${i <= 2 ? value : yen(value)}</td>`).join("");
      return `<tr${hasShortfall ? ' class="shortfall-row"' : ""}>${cells}</tr>`;
    })
    .join("");

  document.getElementById("monthly-detail-table").innerHTML =
    `<table><thead>${header}</thead><tbody>${rows}</tbody></table>`;
  document.getElementById("monthly-detail-summary").textContent = `表で見る（${monthly.rows.length}行）`;
}

function renderResults(output) {
  document.getElementById("results-empty").hidden = true;
  document.getElementById("results-content").hidden = false;

  renderKpiCards(output.dashboard);

  const networthChart = output.charts.networth_chart;
  if (networthChart) {
    renderNetworthChart(networthChart);
  }

  renderMontecarloSection(output);
  renderSensitivityTable(output.tables.sensitivity_table);
  renderMonthlyDetailTable(output.tables.monthly_detail);
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
