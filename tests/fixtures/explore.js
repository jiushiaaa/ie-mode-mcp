// Shared local fixture, compatible with IE7 document mode.
var region = document.createElement('div');
region.id = 'exploreRegion';
for (var blank = 0; blank < 20; blank++) region.appendChild(document.createTextNode('   \n'));
var hiddenSelect = document.createElement('select');
hiddenSelect.style.display = 'none';
var hiddenOption = document.createElement('option');
hiddenOption.appendChild(document.createTextNode('EXPLORE_HIDDEN_OPTION'));
hiddenSelect.appendChild(hiddenOption);
region.appendChild(hiddenSelect);
var text = document.createElement('p');
text.id = 'longText';
text.appendChild(document.createTextNode(new Array(1601).join('Page text. ')));
region.appendChild(text);
for (var i = 0; i < 220; i++) {
    var button = document.createElement('button');
    button.id = 'exploreButton' + i;
    button.appendChild(document.createTextNode('Explore item ' + i));
    region.appendChild(button);
}
var field = document.createElement('input');
field.id = 'exploreField';
region.appendChild(field);
document.body.appendChild(region);
