(() => {
 const directory = document.querySelector('[data-discovery-directory]');
 if (!directory) return;
 const form = directory.querySelector('.discovery-controls');
 const query = form.querySelector('[name="q"]');
 const group = form.querySelector('[name="group"]');
 const reset = form.querySelector('[type="reset"]');
 const result = directory.querySelector('.discovery-result');
 const empty = directory.querySelector('.discovery-empty');
 const sections = [...directory.querySelectorAll('[data-discovery-section]')];
 const entries = [...directory.querySelectorAll('[data-discovery-entry]')].map(marker => ({
  card: marker.closest('[data-cva-item-index]'),
  group: marker.dataset.discoveryGroup,
  text: marker.dataset.discoverySearch.normalize('NFKC').toLocaleLowerCase('ko')
 }));
 const groups = new Set([...group.options].map(option => option.value));
 let timer;
 const update = (writeUrl = true) => {
  clearTimeout(timer);
  const terms = query.value.normalize('NFKC').trim().toLocaleLowerCase('ko').split(/\s+/).filter(Boolean);
  let count = 0;
  const visibleGroups = new Set();
  for (const entry of entries) {
   const visible = (!group.value || group.value === entry.group) && terms.every(term => entry.text.includes(term));
   entry.card.hidden = !visible;
   if (visible) { count++; visibleGroups.add(entry.group); }
  }
  for (const section of sections) section.hidden = !visibleGroups.has(section.dataset.discoverySection);
  empty.hidden = count > 0;
  result.textContent = count === entries.length ? `${count}개 본문` : `${entries.length}개 중 ${count}개 본문`;
  reset.disabled = !query.value && !group.value;
  if (writeUrl) {
   const url = new URL(location.href);
   query.value.trim() ? url.searchParams.set('q', query.value.trim()) : url.searchParams.delete('q');
   group.value ? url.searchParams.set('group', group.value) : url.searchParams.delete('group');
   history.replaceState(null, '', url);
  }
 };
 const restore = () => {
  const url = new URL(location.href);
  query.value = url.searchParams.get('q') || '';
  const selected = url.searchParams.get('group') || '';
  group.value = groups.has(selected) ? selected : '';
  update(false);
 };
 query.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(update, 200); });
 group.addEventListener('change', () => update());
 form.addEventListener('submit', event => { event.preventDefault(); update(); });
 form.addEventListener('reset', event => {
  event.preventDefault(); query.value = ''; group.value = ''; update(); query.focus();
 });
 directory.querySelectorAll('.discovery-jump a').forEach(link => link.addEventListener('click', event => {
  const id = link.hash.slice('#group-'.length);
  if (!groups.has(id)) return;
  event.preventDefault(); query.value = ''; group.value = id; update();
  const section = sections.find(section => section.dataset.discoverySection === id);
  const url = new URL(location.href); url.hash = link.hash; history.replaceState(null, '', url);
  section.scrollIntoView({block: 'start'}); section.focus({preventScroll: true});
 }));
 addEventListener('popstate', restore);
 restore();
})();
