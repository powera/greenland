/*
 * Shared behaviour for the /sync difference pages.
 *
 * Only one thing needs scripting: setting every visible row's action at once.
 * It affects the rendered page only - applying an action to rows on other
 * pages goes through the bulk-apply form, which is an ordinary POST.
 */

/**
 * Check or uncheck every row checkbox on the page.
 *
 * Only the rendered page is affected; the "include rows not shown" form below
 * the table is what reaches the rest of the list.
 *
 * @param {boolean} checked - Whether the boxes should end up checked.
 */
function syncToggleAll(checked) {
    document.querySelectorAll('.item-checkbox').forEach(function (checkbox) {
        checkbox.checked = checked;
    });
    var header = document.getElementById('select-all-checkbox');
    if (header) {
        header.checked = checked;
    }
}

/**
 * Set every action select on the page to `action`, where that row offers it.
 *
 * Rows that cannot offer the action (an empty release value has nothing to
 * copy, so no "use release" option is rendered) are left alone rather than
 * forced to some other choice.
 *
 * @param {string} action - "skip", "use_db" or "use_release".
 */
function syncSelectAll(action) {
    document.querySelectorAll('.action-select').forEach(function (select) {
        for (var index = 0; index < select.options.length; index++) {
            if (select.options[index].value === action) {
                select.selectedIndex = index;
                break;
            }
        }
    });
}
