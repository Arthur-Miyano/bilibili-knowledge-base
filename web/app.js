(() => {
  "use strict";

  const form = document.querySelector("#publish-form");
  const sourceInput = document.querySelector("#source");
  const vaultInput = document.querySelector("#vault");
  const providerInput = document.querySelector("#text-provider");
  const textModelInput = document.querySelector("#text-model");
  const textModelHint = document.querySelector("#text-model-hint");
  const groqModelInput = document.querySelector("#groq-model");
  const groqKeyInput = document.querySelector("#groq-api-key");
  const bilibiliCookieInput = document.querySelector("#bilibili-cookie");
  const bilibiliLoginStart = document.querySelector("#bilibili-login-start");
  const bilibiliLoginLogout = document.querySelector("#bilibili-login-logout");
  const bilibiliLoginStatus = document.querySelector("#bilibili-login-status");
  const bilibiliQrPanel = document.querySelector("#bilibili-qr-panel");
  const bilibiliQrCode = document.querySelector("#bilibili-qr-code");
  const providerKeyInputs = {
    gemini: document.querySelector("#gemini-api-key"),
    deepseek: document.querySelector("#deepseek-api-key"),
    kimi: document.querySelector("#kimi-api-key"),
  };
  const button = document.querySelector("#publish-button");
  const result = document.querySelector("#result-section");
  const resultMessage = document.querySelector("#result-message");
  const resultFiles = document.querySelector("#result-files");
  const copyFilesButton = document.querySelector("#copy-files-button");
  const copyFeedback = document.querySelector("#copy-feedback");
  const recovery = document.querySelector("#recovery");
  const statusSummary = document.querySelector("#status-summary");
  const navButtons = [...document.querySelectorAll("[data-view-target]")];
  const views = [...document.querySelectorAll("[data-view]")];
  const stepNames = ["source", "cloud", "vault"];
  const statusNames = ["ffmpeg", "bilibili_api", "groq", "gemini", "deepseek", "kimi"];
  const VAULT_STORAGE_KEY = "bilibili-knowledge-base.vault";
  const providerEnvNames = {
    gemini: "GEMINI_API_KEY",
    deepseek: "DEEPSEEK_API_KEY",
    kimi: "MOONSHOT_API_KEY",
  };
  let providerStatuses = {};
  const viewCopy = {
    create: ["创建知识库", "从 B 站内容生成 Obsidian 笔记"],
    settings: ["模型与凭据", "选择供应商、具体模型和本次凭据"],
    status: ["运行状态", "检查本机依赖与云端配置"],
  };
  const modelCatalog = {
    gemini: {
      hint: "Gemini 3.5 Flash Lite 成本更低；Flash 适合更复杂的长内容整理。",
      models: [
        ["gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite · 轻量默认"],
        ["gemini-3.5-flash", "Gemini 3.5 Flash · 更强整理"],
      ],
    },
    deepseek: {
      hint: "DeepSeek V4 Flash 速度与成本平衡；V4 Pro 更适合复杂内容。",
      models: [
        ["deepseek-v4-flash", "DeepSeek V4 Flash · 推荐"],
        ["deepseek-v4-pro", "DeepSeek V4 Pro · 更强推理"],
      ],
    },
    kimi: {
      hint: "Kimi K2.6 速度与成本更平衡；K3 适合超长内容和深度整理。",
      models: [
        ["kimi-k2.6", "Kimi K2.6 · 平衡默认"],
        ["kimi-k3", "Kimi K3 · 旗舰长上下文"],
      ],
    },
  };

  const switchView = (name, updateHash = true) => {
    if (!viewCopy[name]) name = "create";
    views.forEach((view) => { view.hidden = view.dataset.view !== name; });
    navButtons.forEach((item) => {
      const selected = item.dataset.viewTarget === name;
      item.setAttribute("aria-selected", selected ? "true" : "false");
      item.tabIndex = selected ? 0 : -1;
    });
    document.querySelector("#view-title").textContent = viewCopy[name][0];
    document.querySelector("#view-description").textContent = viewCopy[name][1];
    if (updateHash && window.location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
    window.scrollTo({ top: 0, behavior: "auto" });
  };

  const updateProvider = () => {
    const provider = providerInput.value;
    const catalog = modelCatalog[provider];
    textModelInput.replaceChildren(...catalog.models.map(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      return option;
    }));
    textModelHint.textContent = catalog.hint;
    document.querySelectorAll("[data-provider-key]").forEach((field) => {
      field.hidden = field.dataset.providerKey !== provider;
    });
  };

  const setStep = (name, state) => {
    const step = document.querySelector(`[data-step="${name}"]`);
    if (step) step.dataset.state = state;
  };

  const resetSteps = () => stepNames.forEach((name) => setStep(name, "idle"));

  const showFieldError = (input, message) => {
    const field = input.closest(".field");
    const error = document.querySelector(`#${input.id}-error`);
    field.dataset.invalid = message ? "true" : "false";
    if (message) {
      error.textContent = message;
      input.setAttribute("aria-invalid", "true");
    } else {
      error.textContent = "";
      input.removeAttribute("aria-invalid");
    }
  };

  const validate = () => {
    let valid = true;
    if (!sourceInput.value.trim()) {
      showFieldError(sourceInput, "请输入 B 站 BV 号或链接。");
      valid = false;
    } else showFieldError(sourceInput, "");
    if (!vaultInput.value.trim()) {
      showFieldError(vaultInput, "请输入 Obsidian Vault 路径。");
      valid = false;
    } else showFieldError(vaultInput, "");
    const modelPattern = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;
    [[textModelInput, "整理模型"], [groqModelInput, "语音识别模型"]].forEach(([input, label]) => {
      if (!modelPattern.test(input.value.trim())) {
        showFieldError(input, `${label} ID 无效。`);
        valid = false;
      } else showFieldError(input, "");
    });
    if (!valid) {
      if (!sourceInput.value.trim() || !vaultInput.value.trim()) {
        switchView("create");
        (sourceInput.value.trim() ? vaultInput : sourceInput).focus();
      } else {
        switchView("settings");
        textModelInput.focus();
      }
      return false;
    }
    const provider = providerInput.value;
    const providerKey = providerKeyInputs[provider];
    const providerStatus = providerStatuses[provider];
    if (!providerKey.value.trim() && providerStatus && !providerStatus.ready) {
      showFieldError(
        providerKey,
        `当前未检测到 ${providerEnvNames[provider]}，请填写本次 Key，或配置环境变量后重试。`,
      );
      switchView("settings");
      providerKey.focus();
      return false;
    }
    return true;
  };

  const setLoading = (loading) => {
    button.disabled = loading;
    form.setAttribute("aria-busy", loading ? "true" : "false");
    button.dataset.loading = loading ? "true" : "false";
    button.querySelector(".button-label").textContent = loading ? "正在整理并发布…" : "生成并发布知识库笔记";
  };

  const clearCredentials = () => {
    [...Object.values(providerKeyInputs), groqKeyInput, bilibiliCookieInput].forEach((input) => {
      input.value = "";
      const state = document.querySelector(`[data-credential-state="${input.id}"]`);
      if (state) state.textContent = "使用环境变量";
    });
  };

  const showResult = (state, message, files = [], advice = "") => {
    const safeFiles = Array.isArray(files) ? files : [];
    result.hidden = false;
    result.setAttribute("aria-busy", state === "loading" ? "true" : "false");
    result.dataset.state = state;
    resultMessage.textContent = message;
    resultFiles.replaceChildren(...safeFiles.map((file) => {
      const item = document.createElement("li");
      item.textContent = file;
      return item;
    }));
    copyFilesButton.hidden = state !== "success" || safeFiles.length === 0;
    copyFeedback.textContent = "";
    recovery.hidden = !advice;
    recovery.textContent = advice;
  };

  const copyFilePaths = async () => {
    const paths = [...resultFiles.querySelectorAll("li")].map((item) => item.textContent).join("\n");
    try {
      await navigator.clipboard.writeText(paths);
      copyFeedback.textContent = "已复制文件路径。";
    } catch (error) {
      copyFeedback.textContent = "复制失败，请手动选择路径。";
    }
  };

  const updateStatus = (payload) => {
    const statuses = payload && payload.statuses ? payload.statuses : {};
    providerStatuses = statuses;
    let ready = 0;
    statusNames.forEach((key) => {
      const item = document.querySelector(`[data-status="${key}"]`);
      const state = statuses[key] && statuses[key].ready ? "ready" : "missing";
      item.dataset.state = state;
      item.querySelector(".status-value").textContent = statuses[key] && statuses[key].label ? statuses[key].label : (state === "ready" ? "已就绪" : "未配置");
      if (state === "ready") ready += 1;
    });
    statusSummary.textContent = `${ready}/${statusNames.length} 项就绪`;
  };

  const loadStatus = async () => {
    try {
      const response = await fetch("/api/status", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("status");
      updateStatus(await response.json());
    } catch (error) {
      statusSummary.textContent = "状态不可用";
      statusNames.forEach((key) => {
        const item = document.querySelector(`[data-status="${key}"]`);
        item.dataset.state = "error";
        item.querySelector(".status-value").textContent = "无法检查";
      });
    }
  };

  const qrStatusLabels = {
    idle: "未开始",
    pending: "待扫码",
    confirm: "待确认",
    logged_in: "已登录",
    expired: "过期",
    failed: "失败",
    logged_out: "已退出",
  };
  let qrPollTimer = null;
  const stopQrPolling = () => {
    if (qrPollTimer !== null) window.clearTimeout(qrPollTimer);
    qrPollTimer = null;
  };
  const showQrStatus = (status, message = "") => {
    bilibiliLoginStatus.textContent = `${qrStatusLabels[status] || "状态未知"}：${message}`;
    bilibiliLoginStatus.dataset.state = status;
    bilibiliQrPanel.hidden = !["pending", "confirm"].includes(status);
    if (["logged_in", "expired", "failed", "logged_out"].includes(status)) {
      bilibiliQrCode.removeAttribute("src");
    }
    bilibiliLoginStart.hidden = status === "logged_in";
    bilibiliLoginLogout.hidden = !["pending", "confirm", "logged_in"].includes(status);
  };
  const scheduleQrCheck = () => {
    stopQrPolling();
    qrPollTimer = window.setTimeout(checkQrLogin, 1500);
  };
  const checkQrLogin = async () => {
    qrPollTimer = null;
    try {
      const response = await fetch("/api/bilibili/login/check", { headers: { Accept: "application/json" } });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "无法检查扫码状态。");
      showQrStatus(payload.status || "failed", payload.message || "");
      if (["pending", "confirm"].includes(payload.status)) scheduleQrCheck();
    } catch (error) {
      showQrStatus("failed", error.message || "无法检查扫码状态，请重试。");
    }
  };
  const startQrLogin = async () => {
    stopQrPolling();
    bilibiliLoginStart.disabled = true;
    showQrStatus("pending", "正在生成二维码…");
    try {
      const response = await fetch("/api/bilibili/login/start", {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || typeof payload.qr_code !== "string" || !payload.qr_code.startsWith("data:image/png;base64,")) {
        throw new Error(payload.error || "二维码生成失败，请重试。");
      }
      bilibiliQrCode.src = payload.qr_code;
      showQrStatus(payload.status || "pending", payload.message || "请使用 B 站 App 扫码。");
      scheduleQrCheck();
    } catch (error) {
      showQrStatus("failed", error.message || "二维码生成失败，请重试。");
    } finally {
      bilibiliLoginStart.disabled = false;
    }
  };
  const logoutQrLogin = async () => {
    stopQrPolling();
    bilibiliLoginLogout.disabled = true;
    try {
      const response = await fetch("/api/bilibili/login/logout", {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "退出登录失败，请重试。");
      bilibiliQrCode.removeAttribute("src");
      showQrStatus(payload.status || "logged_out", payload.message || "已清除本机内存中的 B站登录。");
    } catch (error) {
      showQrStatus("failed", error.message || "退出登录失败，请重试。");
    } finally {
      bilibiliLoginLogout.disabled = false;
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!validate()) return;
    switchView("create");
    resetSteps();
    setLoading(true);
    showResult("loading", "正在读取来源并准备发布…");
    setStep("source", "active");
    let cloudPhaseStarted = false;
    const cloudTimer = window.setTimeout(() => {
      cloudPhaseStarted = true;
      setStep("cloud", "active");
    }, 450);
    const provider = providerInput.value;
    try {
      const response = await fetch("/api/publish", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          source: sourceInput.value.trim(),
          vault: vaultInput.value.trim(),
          text_provider: provider,
          text_model: textModelInput.value,
          [`${provider}_api_key`]: providerKeyInputs[provider].value,
          groq_model: groqModelInput.value,
          groq_api_key: groqKeyInput.value,
          bilibili_cookie: bilibiliCookieInput.value,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "发布失败，请稍后重试。");
      window.clearTimeout(cloudTimer);
      setStep("source", "complete");
      setStep("cloud", "complete");
      setStep("vault", "active");
      const completionDelay = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 180;
      window.setTimeout(() => {
        setStep("vault", "complete");
        showResult("success", payload.message || "知识库笔记已发布到 Obsidian Vault。", payload.files || []);
      }, completionDelay);
    } catch (error) {
      window.clearTimeout(cloudTimer);
      if (cloudPhaseStarted) {
        setStep("source", "complete");
        setStep("cloud", "error");
      } else setStep("source", "error");
      showResult("error", error.message || "发布失败。", [], "请检查 B 站链接、Vault 路径、当前模型和运行状态；如果问题持续，请查看终端中的错误信息。");
    } finally {
      clearCredentials();
      setLoading(false);
    }
  };

  navButtons.forEach((item, index) => {
    item.addEventListener("click", () => switchView(item.dataset.viewTarget));
    item.addEventListener("keydown", (event) => {
      if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) return;
      event.preventDefault();
      const direction = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1;
      const next = navButtons[(index + direction + navButtons.length) % navButtons.length];
      switchView(next.dataset.viewTarget);
      next.focus();
    });
  });
  document.querySelectorAll("[data-view-link]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.viewLink));
  });
  providerInput.addEventListener("change", updateProvider);
  vaultInput.addEventListener("change", () => {
    try {
      const value = vaultInput.value.trim();
      if (value) window.localStorage.setItem(VAULT_STORAGE_KEY, value);
      else window.localStorage.removeItem(VAULT_STORAGE_KEY);
    } catch {}
  });
  [sourceInput, vaultInput, textModelInput, groqModelInput, ...Object.values(providerKeyInputs), groqKeyInput, bilibiliCookieInput].forEach((input) => {
    input.addEventListener("input", () => {
      if (document.querySelector(`#${input.id}-error`)) showFieldError(input, "");
      const state = document.querySelector(`[data-credential-state="${input.id}"]`);
      if (state) state.textContent = input.value ? "本次已填写" : "使用环境变量";
    });
  });
  copyFilesButton.addEventListener("click", copyFilePaths);
  bilibiliLoginStart.addEventListener("click", startQrLogin);
  bilibiliLoginLogout.addEventListener("click", logoutQrLogin);
  form.addEventListener("submit", submit);
  window.addEventListener("hashchange", () => switchView(window.location.hash.slice(1), false));

  updateProvider();
  try {
    const savedVault = window.localStorage.getItem(VAULT_STORAGE_KEY);
    if (savedVault) vaultInput.value = savedVault;
  } catch {}
  switchView(window.location.hash.slice(1) || "create", false);
  loadStatus();
  checkQrLogin();
})();
