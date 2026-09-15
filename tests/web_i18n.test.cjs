const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const root = path.join(__dirname, '..');
function runtime() {
    const label = {dataset: {i18n: 'Calendário'}, textContent: ''};
    const document = {
        documentElement: {lang: 'pt'},
        getElementById: () => ({textContent: fs.readFileSync(path.join(root, 'app/translations/en.json'), 'utf8')}),
        querySelectorAll: selector => selector === '[data-i18n]' ? [label] : [],
    };
    const context = {window: {}, document};
    vm.runInNewContext(fs.readFileSync(path.join(root, 'app/static/i18n.js'), 'utf8'), context);
    return {...context.window.SIGCPI18n, document, label};
}

test('switches language and locale in both directions without losing source labels', () => {
    const i18n = runtime();
    i18n.setLanguage('en');
    assert.equal(i18n.label.textContent, 'Calendar');
    assert.equal(i18n.document.documentElement.lang, 'en');
    assert.equal(i18n.locale(), 'en-GB');
    assert.equal(i18n.t('Almoço'), 'Lunch');
    i18n.setLanguage('pt');
    assert.equal(i18n.label.textContent, 'Calendário');
    assert.equal(i18n.t('Almoço'), 'Almoço');
    assert.equal(i18n.locale(), 'pt-PT');
});

test('interpolates complete messages and preserves names and replacement characters', () => {
    const i18n = runtime();
    i18n.setLanguage('en');
    assert.equal(i18n.t('Queres remover {0} desta Team?', 'João $&'), 'Remove João $& from this Team?');
    assert.equal(i18n.t('João $& submeteu um período para decisão.'), 'João $& submitted a period for a decision.');
    assert.equal(i18n.t('Bacalhau à Brás'), 'Bacalhau à Brás');
    assert.equal(i18n.t('Pendente'), 'Pending');
    assert.equal(i18n.t('A ausência tem 31 dias; o limite configurado é 30.'), 'The absence lasts 31 days; the configured limit is 30.');
});

test('unsupported languages fall back to Portuguese', () => {
    const i18n = runtime();
    i18n.setLanguage('fr');
    assert.equal(i18n.t('Guardar'), 'Guardar');
    assert.equal(i18n.document.documentElement.lang, 'pt');
});
