// The walkthrough. Each beat dims the page, lifts one region above the scrim inside a
// ring, and captions it beside it. Beat 0 is the opening card and the one after the last
// beat is the closing card. The URL keeps the beat number, so #6 opens on the sixth beat.

(function () {
  'use strict';

  var beats = JSON.parse(document.getElementById('beats').textContent);
  var byId = function (id) { return document.getElementById(id); };
  var STATUS = {
    'Received': 'received', 'Read': 'read', 'Needs an answer': 'needs_answer', 'Ready': 'ready',
    'Enriched': 'enriched', 'Awaiting approval': 'awaiting_approval', 'Approved': 'approved', 'Sent': 'sent'
  };
  var step = 0;

  function fromHash() {
    var n = parseInt((location.hash || '').replace('#', ''), 10);
    return isNaN(n) ? 0 : n;
  }

  function clear() {
    document.querySelectorAll('.lit').forEach(function (el) { el.classList.remove('lit'); });
    document.querySelectorAll('#t-sheet [data-line].highlight').forEach(function (el) { el.classList.remove('highlight'); });
    document.querySelectorAll('[data-row].is-active').forEach(function (el) { el.classList.remove('is-active'); });
  }

  function show(beat, index) {
    document.querySelectorAll('.tour-panel').forEach(function (panel) {
      panel.classList.toggle('is-shown', panel.getAttribute('data-panel') === beat.panel);
    });

    document.querySelectorAll('#t-stages li').forEach(function (li, i) {
      li.className = i < beat.stage ? 'done' : (i === beat.stage ? 'current' : '');
    });

    var status = byId('t-status');
    status.textContent = beat.status;
    status.className = 'status status-' + (STATUS[beat.status] || 'received');

    if (beat.line) {
      var line = document.querySelector('#t-sheet [data-line="' + beat.line + '"]');
      if (line) line.classList.add('highlight');
    }
    if (beat.select) {
      var row = document.querySelector('[data-row="' + beat.select + '"]');
      if (row) row.classList.add('is-active');
    }

    var target = beat.target ? byId(beat.target) : null;
    if (target) target.classList.add('lit');

    document.querySelectorAll('#acts [data-act]').forEach(function (el) {
      el.classList.toggle('on', Number(el.getAttribute('data-act')) === beat.act);
    });
    byId('cap-count').textContent = (index < 10 ? '0' : '') + index + ' of ' + beats.length;
    byId('cap-title').textContent = beat.title;
    byId('cap-body').textContent = beat.body;
    byId('cap-next').textContent = index === beats.length ? 'Finish' : 'Next';

    if (target) bringIntoView(target);
  }

  // Put the lit region in the part of the screen the caption does not cover.
  function bringIntoView(target) {
    var caption = byId('caption');
    var side = window.matchMedia('(min-width: 1180px)').matches;
    var covered = side ? 0 : caption.getBoundingClientRect().height + 16;
    var room = window.innerHeight - covered;
    var box = target.getBoundingClientRect();
    var top = window.scrollY + box.top;
    var y = box.height + 48 < room ? top - (room - box.height) / 2 : top - 24;
    window.scrollTo({ top: Math.max(0, y), behavior: 'auto' });
  }

  function go(n) {
    n = Math.max(0, Math.min(beats.length + 1, n));
    step = n;
    var onBeat = n >= 1 && n <= beats.length;
    clear();
    byId('intro').classList.toggle('hidden', n !== 0);
    byId('ending').classList.toggle('hidden', n !== beats.length + 1);
    byId('caption').hidden = !onBeat;
    document.body.classList.toggle('beat', onBeat);
    if (onBeat) show(beats[n - 1], n);
    if (fromHash() !== n) history.replaceState(null, '', n ? '#' + n : location.pathname);
  }

  byId('start').addEventListener('click', function () { go(1); });
  byId('replay').addEventListener('click', function () { go(1); });
  byId('cap-next').addEventListener('click', function () { go(step + 1); });
  byId('cap-back').addEventListener('click', function () { go(step - 1); });

  document.addEventListener('keydown', function (e) {
    if (e.target.closest('input, textarea, select')) return;
    if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); go(step + 1); }
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); go(step - 1); }
    if (e.key === 'Escape') { go(0); }
  });
  window.addEventListener('hashchange', function () { go(fromHash()); });
  window.addEventListener('resize', function () {
    var lit = document.querySelector('.lit');
    if (lit) bringIntoView(lit);
  });

  go(fromHash());
})();
