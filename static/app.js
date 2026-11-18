/* 会记 · AI 会议纪要助手 —— 前端交互 */
document.addEventListener("DOMContentLoaded", () => {
  // 危险操作二次确认
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // AI 提炼纪要
  const extractBtn = document.getElementById("extract-btn");
  if (extractBtn) {
    extractBtn.addEventListener("click", async () => {
      const originalText = extractBtn.textContent;
      extractBtn.disabled = true;
      extractBtn.textContent = "AI 提炼中，请稍候…";
      try {
        const response = await fetch(extractBtn.dataset.url, {
          method: "POST",
          headers: { Accept: "application/json" },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
          throw new Error(data.error || `请求失败（HTTP ${response.status}）`);
        }
        window.location.reload();
      } catch (error) {
        window.alert("AI 提炼失败：" + error.message);
        extractBtn.disabled = false;
        extractBtn.textContent = originalText;
      }
    });
  }

  // 待办勾选
  document.querySelectorAll(".js-todo-toggle").forEach((checkbox) => {
    checkbox.addEventListener("change", async () => {
      const url = checkbox.dataset.url;
      checkbox.disabled = true;
      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { Accept: "application/json" },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
          throw new Error(data.error || "更新失败");
        }
        window.location.reload();
      } catch (error) {
        window.alert("更新待办失败：" + error.message);
        checkbox.checked = !checkbox.checked;
        checkbox.disabled = false;
      }
    });
  });

  // 记录字数统计
  const transcript = document.getElementById("transcript");
  const counter = document.getElementById("char-count");
  if (transcript && counter) {
    const updateCount = () => {
      counter.textContent = transcript.value.length;
    };
    transcript.addEventListener("input", updateCount);
    updateCount();
  }

  // 成功提示自动淡出
  document.querySelectorAll(".flash-success").forEach((element) => {
    setTimeout(() => {
      element.style.transition = "opacity .4s";
      element.style.opacity = "0";
      setTimeout(() => element.remove(), 400);
    }, 4000);
  });
});
