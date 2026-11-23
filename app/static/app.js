// A few small things: mark the line a value came from, keep the approve button disabled
// until the authority box is ticked, make the upload box answer a chosen or dropped file,
// offer a date picker when a date field is being edited, and follow the design contents.

(function () {
  // --- Mark the source line on the bill -----------------------------------------
  document.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-line-ref]');
    if (!trigger) return;
    var lineId = trigger.getAttribute('data-line-ref');
    if (!lineId) return;

    document.querySelectorAll('.document [data-line].highlight').forEach(function (node) {
      node.classList.remove('highlight');
    });
    document.querySelectorAll('.read-value.is-active').forEach(function (node) {
      node.classList.remove('is-active');
    });

    var target = document.querySelector('.document [data-line="' + lineId + '"]');
    if (!target) return;
    target.classList.add('highlight');
    if (trigger.classList.contains('read-value')) trigger.classList.add('is-active');

    var sheet = target.closest('.sheet');
    if (sheet && sheet.scrollHeight > sheet.clientHeight + 1) {
      var top = target.getBoundingClientRect().top - sheet.getBoundingClientRect().top + sheet.scrollTop;
      sheet.scrollTo({ top: top - sheet.clientHeight / 2, behavior: 'smooth' });
    }
    var box = target.getBoundingClientRect();
    if (box.top < 0 || box.bottom > window.innerHeight) {
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

  // --- Edit form: a date picker for date fields ---------------------------------
  var edit = document.getElementById('edit-form');
  if (edit) {
    var select = edit.querySelector('select');
    var value = edit.querySelector('input[name="value"]');
    var fit = function () {
      var option = select.options[select.selectedIndex];
      value.type = option && option.getAttribute('data-kind') === 'date' ? 'date' : 'text';
    };
    select.addEventListener('change', fit);
    fit();
  }

  // --- Design page contents ----------------------------------------------------
  var links = document.querySelectorAll('.toc a[data-spy]');
  if (links.length && 'IntersectionObserver' in window) {
    var byId = {};
    links.forEach(function (link) { byId[link.getAttribute('data-spy')] = link; });
    var visible = {};
    var chapters = document.querySelectorAll('.chapter');
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) { visible[entry.target.id] = entry.isIntersecting; });
      var first = null;
      chapters.forEach(function (chapter) { if (!first && visible[chapter.id]) first = chapter.id; });
      if (!first) return;
      links.forEach(function (link) { link.classList.remove('is-active'); });
      if (byId[first]) byId[first].classList.add('is-active');
    }, { rootMargin: '-10% 0px -60% 0px' });
    chapters.forEach(function (chapter) { observer.observe(chapter); });
  }
})();
