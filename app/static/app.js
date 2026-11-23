// Two small things: highlight the line a value came from, and keep the approve
// button disabled until the authority box is ticked.

document.addEventListener('click', function (event) {
  var trigger = event.target.closest('[data-line-ref]');
  if (!trigger) return;
  var lineId = trigger.getAttribute('data-line-ref');
  if (!lineId) return;

  document.querySelectorAll('.document [data-line]').forEach(function (node) {
    node.classList.remove('highlight');
  });

  var target = document.querySelector('.document [data-line="' + lineId + '"]');
  if (!target) return;
  target.classList.add('highlight');
  target.scrollIntoView({ block: 'center', behavior: 'smooth' });
});

var authority = document.getElementById('authority');
var approveButton = document.getElementById('approve-button');
if (authority && approveButton) {
  authority.addEventListener('change', function () {
    approveButton.disabled = !authority.checked;
  });
}
