(() => {
  'use strict';
  const toggle = document.querySelector('.nav-toggle');
  const nav = document.querySelector('.main-nav');
  const closeNav = () => { toggle?.setAttribute('aria-expanded', 'false'); nav?.classList.remove('is-open'); };
  toggle?.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    nav.classList.toggle('is-open', open);
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeNav(); });
  document.addEventListener('click', event => { if (!event.target.closest('.header-inner')) closeNav(); });
  document.querySelector('#sort')?.addEventListener('change', event => event.target.form.requestSubmit());
  const questionForm = document.querySelector('#question-form');
  const question = document.querySelector('#id_question');
  document.querySelectorAll('[data-question]').forEach(link => {
    link.addEventListener('click', event => {
      if (!question) return;
      event.preventDefault();
      question.value = link.dataset.question;
      question.focus({ preventScroll: true });
      document.querySelector('#question-search').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' });
    });
  });
  question?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !questionForm.querySelector('[data-run-ai]').disabled) {
      event.preventDefault(); questionForm.requestSubmit();
    }
  });
  questionForm?.addEventListener('submit', () => {
    const button = questionForm.querySelector('[data-run-ai]');
    button.disabled = true;
    button.textContent = 'Je relie les connaissances…';
    questionForm.setAttribute('aria-busy', 'true');
    document.querySelector('#question-help').textContent = 'La recherche peut prendre quelques instants.';
  });
  const advanced = document.querySelector('#advanced-sparql');
  document.querySelectorAll('[data-open-advanced]').forEach(link => {
    link.addEventListener('click', event => {
      if (!advanced) return;
      event.preventDefault(); advanced.open = true;
      advanced.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
    });
  });
  const editor = document.querySelector('#id_query');
  if (!editor) return;
  const numbers = document.querySelector('.line-numbers');
  const updateLines = () => { numbers.textContent = Array.from({ length: editor.value.split('\n').length }, (_, i) => i + 1).join('\n'); numbers.scrollTop = editor.scrollTop; };
  editor.addEventListener('input', updateLines);
  editor.addEventListener('scroll', () => { numbers.scrollTop = editor.scrollTop; });
  updateLines();
  const form = document.querySelector('#query-form');
  advanced?.addEventListener('toggle', updateLines);
  document.querySelector('[data-edit-generated]')?.addEventListener('click', () => {
    editor.value = document.querySelector('#generated-sparql').textContent;
    advanced.open = true;
    document.querySelectorAll('[data-example]').forEach(item => item.classList.remove('is-selected'));
    updateLines();
    advanced.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
    editor.focus({ preventScroll: true });
  });
  editor.addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); form.requestSubmit(); }
    if (event.key === 'Tab' && !event.shiftKey) {
      event.preventDefault();
      editor.setRangeText('  ', editor.selectionStart, editor.selectionEnd, 'end');
      editor.dispatchEvent(new Event('input'));
    }
  });
  const samples = JSON.parse(document.querySelector('#sparql-examples').textContent);
  document.querySelectorAll('[data-example]').forEach(button => {
    button.addEventListener('click', event => {
      const sample = samples.find(item => item.id === button.dataset.example);
      if (!sample) return;
      event.preventDefault();
      editor.value = sample.query;
      updateLines();
      document.querySelectorAll('[data-example]').forEach(item => item.classList.toggle('is-selected', item === button));
      document.querySelector('.query-errors')?.remove();
      const resultHeading = document.querySelector('.query-results-heading h2');
      resultHeading.textContent = 'Résultats · nouvelle requête à exécuter';
      editor.focus({ preventScroll: true });
      document.querySelector('#editeur').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' });
      const url = new URL(window.location.href);
      url.searchParams.set('mode', 'sparql');
      url.searchParams.set('exemple', sample.id);
      history.replaceState(null, '', url.pathname + url.search);
    });
  });
  editor.addEventListener('input', () => {
    document.querySelectorAll('[data-example]').forEach(item => item.classList.remove('is-selected'));
  });
  form.addEventListener('submit', () => {
    const button = document.querySelector('[data-run-query]');
    button.disabled = true;
    button.textContent = 'Interrogation du graphe…';
    form.setAttribute('aria-busy', 'true');
  });
  window.addEventListener('pageshow', event => { if (event.persisted) window.location.reload(); });
  let toastTimer;
  const toast = message => {
    const el = document.querySelector('.copy-toast');
    el.textContent = message;
    el.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('is-visible'), 2600);
  };
  document.querySelector('[data-copy-query]')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(editor.value); toast('Requête copiée.'); }
    catch { editor.focus(); editor.select(); toast('Sélection prête : utilisez Ctrl/Cmd + C.'); }
  });
  document.querySelector('[data-download-results]')?.addEventListener('click', () => {
    const data = JSON.parse(document.querySelector('#sparql-result').textContent);
    const payload = 'boolean' in data ? { head: data.head, boolean: data.boolean } : { head: data.head, results: data.results };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/sparql-results+json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'websemantic-resultats.json';
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
})();
