// A few small things and nothing else: highlight the line a value came from, keep the
// approve button disabled until the authority box is ticked, make the upload box respond
// to a chosen or dropped file, and mark the section of the design page in view.

(function () {
  // --- Highlight the source line on the bill -----------------------------------
  document.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-line-ref]');
    if (!trigger) return;
    var lineId = trigger.getAttribute('data-line-ref');
    if (!lineId) return;

    document.querySelectorAll('.document [data-line].highlight').forEach(function (node) {
      node.classList.remove('highlight');
    });
    document.querySelectorAll('[data-line-ref].is-active').forEach(function (node) {
      node.classList.remove('is-active');
    });

    var target = document.querySelector('.document [data-line="' + lineId + '"]');
    if (!target) return;
    // Restart the glow even when the same line is clicked twice.
    void target.offsetWidth;
    target.classList.add('highlight');
    if (trigger.classList.contains('read-value')) trigger.classList.add('is-active');

    var pane = target.closest('.paper');
    var paneScrolls = pane && pane.scrollHeight > pane.clientHeight + 1;
    if (paneScrolls) {
      var top = target.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
      pane.scrollTo({ top: top - pane.clientHeight / 2, behavior: 'smooth' });
    }
    var box = target.getBoundingClientRect();
    if (box.top < 70 || box.bottom > window.innerHeight) {
      target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  });

  // --- Approve only once the authority box is ticked -------------------------
  var authority = document.getElementById('authority');
  var approveButton = document.getElementById('approve-button');
  if (authority && approveButton) {
    var sync = function () { approveButton.disabled = !authority.checked; };
    authority.addEventListener('change', sync);
    sync();
  }

  // --- Upload box --------------------------------------------------------------
  var drop = document.querySelector('.dropzone');
  if (drop) {
    var input = drop.querySelector('input[type="file"]');
    var text = drop.querySelector('.dropzone-text');
    var button = drop.querySelector('#upload-button');
    var show = function () {
      var file = input.files && input.files[0];
      drop.classList.toggle('has-file', !!file);
      text.textContent = file ? file.name : text.getAttribute('data-empty');
      if (button) button.disabled = !file;
    };
    input.addEventListener('change', show);
    ['dragenter', 'dragover'].forEach(function (name) {
      drop.addEventListener(name, function () { drop.classList.add('is-over'); });
    });
    ['dragleave', 'drop'].forEach(function (name) {
      drop.addEventListener(name, function () { drop.classList.remove('is-over'); });
    });
    show();
  }

  // --- Design page contents ----------------------------------------------------
  var links = document.querySelectorAll('.contents a[data-spy]');
  if (links.length && 'IntersectionObserver' in window) {
    var byId = {};
    links.forEach(function (link) { byId[link.getAttribute('data-spy')] = link; });
    var visible = {};
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) { visible[entry.target.id] = entry.isIntersecting; });
      var first = null;
      document.querySelectorAll('.blocks .block').forEach(function (block) {
        if (!first && visible[block.id]) first = block.id;
      });
      if (!first) return;
      links.forEach(function (link) { link.classList.remove('is-active'); });
      if (byId[first]) byId[first].classList.add('is-active');
    }, { rootMargin: '-80px 0px -55% 0px' });
    document.querySelectorAll('.blocks .block').forEach(function (block) { observer.observe(block); });
  }
})();
