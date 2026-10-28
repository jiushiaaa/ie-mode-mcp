"""Fixed ES3-compatible page inspection; never evaluates caller-supplied code."""

FIND_ELEMENTS = r"""
var query = arguments[0], by = arguments[1], offset = arguments[2], limit = arguments[3];
var nodes = document.getElementsByTagName('*'), matches = [], total = 0;
function visible(el) {
    var css = window.getComputedStyle ? window.getComputedStyle(el) : el.currentStyle;
    return (el.offsetWidth || el.offsetHeight) &&
        !(css && (css.display === 'none' || css.visibility === 'hidden'));
}
function label(el) {
    var text = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || '';
    // Own text nodes only: avoids returning every ancestor of matching text.
    for (var node = el.firstChild; node && text.length < 1000; node = node.nextSibling) {
        if (node.nodeType === 3 && !/^(INPUT|TEXTAREA|SCRIPT|STYLE)$/.test(el.tagName)) text += ' ' + node.nodeValue;
    }
    return text.replace(/\s+/g, ' ').replace(/^\s+|\s+$/g, '').substring(0, 1000);
}
for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (/^(SCRIPT|STYLE|HEAD|META|LINK)$/.test(el.tagName) || !visible(el)) continue;
    var text = label(el), value = by === 'id' ? el.id : by === 'name' ? el.getAttribute('name') :
        by === 'tag' ? el.tagName.toLowerCase() : text.toLowerCase();
    var found = by === 'text' ? value.indexOf(query.toLowerCase()) >= 0 :
        value === (by === 'tag' ? query.toLowerCase() : query);
    if (!found) continue;
    if (total >= offset && matches.length < limit) {
        matches.push({element: el, tag: el.tagName.toLowerCase(), id: el.id || '',
            name: el.getAttribute('name'), label: text});
    }
    total++;
}
return {document: document.documentElement, matches: matches, total: total,
    next_offset: total > offset + matches.length ? offset + matches.length : null,
    frame_url: location.href};
"""
