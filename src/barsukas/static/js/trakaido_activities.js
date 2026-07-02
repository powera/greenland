/**
 * Client-side quiz engine for Trakaido activities in Barsukas.
 *
 * Each activity page embeds a JSON array of questions in a template script
 * block and calls TrakaidoQuiz.init() with a renderer callback that knows
 * how to display one question.
 *
 * Progress is tracked at two layers:
 *  - the current batch of questions, shown as a row of dots that fill in
 *    green/red as they are answered; and
 *  - a cumulative practice session (TrakaidoSession) persisted in
 *    sessionStorage and shared by every activity: total answered, accuracy,
 *    current/best streak, and a per-activity breakdown.  Finishing a batch
 *    offers "keep going" (a plain reload fetches fresh questions while the
 *    session carries on) rather than a hard restart.
 */

var TrakaidoSession = (function () {
  var STORAGE_KEY = "tk-session-v1";

  function _blank(lang) {
    return {
      lang: lang || "",
      startedAt: Date.now(),
      answered: 0,
      correct: 0,
      streak: 0,
      bestStreak: 0,
      activities: {},
    };
  }

  function load(lang) {
    var data = null;
    try {
      var raw = window.sessionStorage.getItem(STORAGE_KEY);
      if (raw) data = JSON.parse(raw);
    } catch (e) {
      data = null;
    }
    if (!data || typeof data.answered !== "number") {
      return _blank(lang);
    }
    // Switching target language starts a fresh session.
    if (lang && data.lang && data.lang !== lang) {
      return _blank(lang);
    }
    return data;
  }

  function _save(data) {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (e) {
      /* private browsing etc. — session stats just won't persist */
    }
  }

  function record(lang, activity, isCorrect) {
    var s = load(lang);
    s.lang = lang || s.lang;
    s.answered++;
    if (isCorrect) {
      s.correct++;
      s.streak++;
      if (s.streak > s.bestStreak) s.bestStreak = s.streak;
    } else {
      s.streak = 0;
    }
    var key = activity || "activity";
    if (!s.activities[key]) s.activities[key] = { answered: 0, correct: 0 };
    s.activities[key].answered++;
    if (isCorrect) s.activities[key].correct++;
    _save(s);
    return s;
  }

  function reset() {
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      /* ignore */
    }
  }

  function accuracy(s) {
    if (!s || s.answered === 0) return 0;
    return Math.round((s.correct / s.answered) * 100);
  }

  function summaryText(s) {
    if (!s || s.answered === 0) return "";
    var text =
      "Session: " + s.answered + " answered · " + accuracy(s) + "% correct";
    if (s.streak >= 2) text += " · streak " + s.streak;
    if (s.bestStreak >= 3) text += " · best " + s.bestStreak;
    return text;
  }

  return {
    load: load,
    record: record,
    reset: reset,
    accuracy: accuracy,
    summaryText: summaryText,
  };
})();

var TrakaidoQuiz = (function () {
  var questions = [];
  var results = []; // per-question: true / false / undefined
  var currentIndex = 0;
  var answered = false;
  var renderer = null;
  var meta = { lang: "", activity: "", indexUrl: "" };

  function init(opts) {
    questions = opts.questions || [];
    renderer = opts.renderer;
    results = [];
    currentIndex = 0;
    answered = false;

    var prog = document.getElementById("tk-progress");
    if (prog) {
      meta.lang = prog.getAttribute("data-lang") || "";
      meta.indexUrl = prog.getAttribute("data-index-url") || "";
    }
    meta.activity = opts.activity || _activityFromPath();

    _bindResetButton();

    if (questions.length === 0) {
      _showEmpty();
      return;
    }

    _renderDots();
    _renderSessionLine(TrakaidoSession.load(meta.lang));
    _showQuestion();
  }

  function _activityFromPath() {
    var parts = window.location.pathname.split("/");
    for (var i = parts.length - 1; i >= 0; i--) {
      if (parts[i]) return parts[i];
    }
    return "activity";
  }

  function _bindResetButton() {
    var btn = document.getElementById("tk-session-reset");
    if (!btn) return;
    btn.addEventListener("click", function () {
      TrakaidoSession.reset();
      _renderSessionLine(TrakaidoSession.load(meta.lang));
    });
  }

  function _showEmpty() {
    var area = document.getElementById("tk-activity-area");
    if (area) {
      area.innerHTML =
        '<div class="trakaido-empty">' +
        "Not enough data at this level to build a quiz. Try a different level." +
        "</div>";
    }
    var prog = document.getElementById("tk-progress");
    if (prog) prog.style.display = "none";
    var nav = document.getElementById("tk-nav-buttons");
    if (nav) nav.style.display = "none";
  }

  function _batchScore() {
    var right = 0;
    var done = 0;
    for (var i = 0; i < results.length; i++) {
      if (results[i] === true) {
        right++;
        done++;
      } else if (results[i] === false) {
        done++;
      }
    }
    return { right: right, done: done };
  }

  function _renderDots() {
    var container = document.getElementById("tk-dots");
    if (!container) return;
    container.innerHTML = "";
    for (var i = 0; i < questions.length; i++) {
      var dot = document.createElement("span");
      dot.className = "tk-dot";
      if (results[i] === true) {
        dot.className += " tk-dot-correct";
      } else if (results[i] === false) {
        dot.className += " tk-dot-wrong";
      } else if (i === currentIndex) {
        dot.className += " tk-dot-current";
      }
      container.appendChild(dot);
    }
    var scoreEl = document.getElementById("tk-batch-score");
    if (scoreEl) {
      var s = _batchScore();
      scoreEl.textContent = s.done > 0 ? s.right + "/" + s.done + " this round" : "";
    }
  }

  function _renderSessionLine(session) {
    var el = document.getElementById("tk-session-line");
    if (el) {
      el.textContent = TrakaidoSession.summaryText(session);
    }
    var btn = document.getElementById("tk-session-reset");
    if (btn) {
      btn.style.visibility = session && session.answered > 0 ? "visible" : "hidden";
    }
  }

  function _showQuestion() {
    answered = false;
    _renderDots();
    if (renderer) {
      renderer(questions[currentIndex], currentIndex);
    }
    var nextBtn = document.getElementById("tk-next-btn");
    if (nextBtn) nextBtn.disabled = true;
  }

  function recordAnswer(isCorrect) {
    if (answered) return;
    answered = true;
    results[currentIndex] = !!isCorrect;
    var session = TrakaidoSession.record(meta.lang, meta.activity, !!isCorrect);
    _renderDots();
    _renderSessionLine(session);
    var nextBtn = document.getElementById("tk-next-btn");
    if (nextBtn) {
      nextBtn.disabled = false;
      if (currentIndex === questions.length - 1) {
        nextBtn.innerHTML = "Finish round &#8594;";
      }
    }
  }

  function next() {
    if (!answered) return;
    currentIndex++;
    if (currentIndex >= questions.length) {
      _showRoundComplete();
    } else {
      _showQuestion();
    }
  }

  function _showRoundComplete() {
    var area = document.getElementById("tk-activity-area");
    var s = _batchScore();
    var session = TrakaidoSession.load(meta.lang);
    var pct = questions.length > 0 ? Math.round((s.right / questions.length) * 100) : 0;

    if (area) {
      var html =
        '<div class="tk-round-card">' +
        '<div class="tk-round-headline">' +
        s.right + " / " + questions.length + " this round (" + pct + "%)" +
        "</div>";
      var sessionText = TrakaidoSession.summaryText(session);
      if (sessionText) {
        html += '<div class="tk-round-session">' + _escapeHtml(sessionText) + "</div>";
      }
      html +=
        '<div class="tk-round-actions">' +
        '<button class="trakaido-button" onclick="location.reload()">' +
        "Keep going &#8594;</button>";
      if (meta.indexUrl) {
        html +=
          '<a class="tk-round-link" href="' +
          _escapeAttr(meta.indexUrl) +
          '">Choose another activity</a>';
      }
      html += "</div></div>";
      area.innerHTML = html;
    }

    _renderDots();
    var nav = document.getElementById("tk-nav-buttons");
    if (nav) nav.style.display = "none";
  }

  function _escapeHtml(s) {
    var d = document.createElement("div");
    d.appendChild(document.createTextNode(s));
    return d.innerHTML;
  }

  function _escapeAttr(s) {
    return _escapeHtml(s).replace(/"/g, "&quot;");
  }

  function getCurrentIndex() {
    return currentIndex;
  }

  return { init: init, recordAnswer: recordAnswer, next: next, getCurrentIndex: getCurrentIndex };
})();

/* Session summary on the activities index page. */
document.addEventListener("DOMContentLoaded", function () {
  var summary = document.getElementById("tk-session-summary");
  if (!summary) return;
  var session = TrakaidoSession.load(null);
  var text = TrakaidoSession.summaryText(session);
  if (!text) return;
  var line = document.createElement("span");
  line.className = "tk-session-line";
  line.textContent = text;
  var reset = document.createElement("button");
  reset.type = "button";
  reset.className = "tk-session-reset";
  reset.textContent = "Reset session";
  reset.addEventListener("click", function () {
    TrakaidoSession.reset();
    summary.hidden = true;
  });
  summary.appendChild(line);
  summary.appendChild(reset);
  summary.hidden = false;
});
