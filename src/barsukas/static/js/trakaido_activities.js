/**
 * Client-side quiz engine for Trakaido activities in Barsukas.
 *
 * Each activity page embeds a JSON array of questions in a global variable
 * (window.TK_QUESTIONS) and calls TrakaidoQuiz.init() with a renderer
 * callback that knows how to display one question.
 */
var TrakaidoQuiz = (function () {
  var questions = [];
  var currentIndex = 0;
  var score = 0;
  var answered = false;
  var renderer = null;

  function init(opts) {
    questions = opts.questions || [];
    renderer = opts.renderer;
    currentIndex = 0;
    score = 0;
    answered = false;

    if (questions.length === 0) {
      _showEmpty();
      return;
    }

    _updateProgress();
    _showQuestion();
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

  function _updateProgress() {
    var el = document.getElementById("tk-progress-text");
    if (el) {
      el.textContent =
        "Question " +
        (currentIndex + 1) +
        " of " +
        questions.length +
        "  |  Score: " +
        score +
        "/" +
        (currentIndex + (answered ? 1 : 0));
    }
    var bar = document.getElementById("tk-progress-bar");
    if (bar) {
      bar.style.width = ((currentIndex / questions.length) * 100).toFixed(1) + "%";
    }
  }

  function _showQuestion() {
    answered = false;
    _updateProgress();
    if (renderer) {
      renderer(questions[currentIndex], currentIndex);
    }
    var nextBtn = document.getElementById("tk-next-btn");
    if (nextBtn) nextBtn.disabled = true;
  }

  function recordAnswer(isCorrect) {
    if (answered) return;
    answered = true;
    if (isCorrect) score++;
    _updateProgress();
    var nextBtn = document.getElementById("tk-next-btn");
    if (nextBtn) nextBtn.disabled = false;
  }

  function next() {
    if (!answered) return;
    currentIndex++;
    if (currentIndex >= questions.length) {
      _showResults();
    } else {
      _showQuestion();
    }
  }

  function _showResults() {
    var area = document.getElementById("tk-activity-area");
    var pct = questions.length > 0 ? Math.round((score / questions.length) * 100) : 0;
    var emoji = pct >= 80 ? "&#9733;" : pct >= 50 ? "&#9675;" : "&#9744;";
    if (area) {
      area.innerHTML =
        '<div class="trakaido-card" style="text-align:center;padding:2rem">' +
        '<div style="font-size:3rem;margin-bottom:0.5rem">' + emoji + "</div>" +
        "<h2>Round Complete</h2>" +
        '<p style="font-size:1.3rem;margin:0.75rem 0">' +
        score + " / " + questions.length + " correct (" + pct + "%)" +
        "</p>" +
        '<button class="trakaido-button" onclick="location.reload()">Play Again</button>' +
        "</div>";
    }
    var bar = document.getElementById("tk-progress-bar");
    if (bar) bar.style.width = "100%";
    var nav = document.getElementById("tk-nav-buttons");
    if (nav) nav.style.display = "none";
  }

  function getCurrentIndex() {
    return currentIndex;
  }

  return { init: init, recordAnswer: recordAnswer, next: next, getCurrentIndex: getCurrentIndex };
})();
