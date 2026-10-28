"""Read-only probes using syntax supported by legacy IE document modes."""

READY_PROBE = """
    var complete=true, docs=0, skipped=0, elements=0, hash=0;
    function add(text) {
        // Hash locally so page markup and field contents are not returned.
        for(var j=0;j<text.length;j++) hash=((hash<<5)-hash+text.charCodeAt(j))|0;
    }
    function inspect(doc, win) {
        docs++;
        if(doc.readyState!=='complete') complete=false;
        elements+=doc.getElementsByTagName('*').length;
        add(doc.URL || '');
        add(doc.documentElement ? doc.documentElement.outerHTML : '');
        if(!argumentsIncludeFrames) return;
        for(var i=0;i<win.frames.length;i++) {
            var child;
            try { child=win.frames[i].document; }
            catch(e) { skipped++; continue; }
            inspect(child,win.frames[i]);
        }
    }
    var argumentsIncludeFrames=arguments[0];
    inspect(document,window);
    return {document:document.documentElement, signature:String(hash)+':'+docs+':'+skipped,
            complete:complete, documents:docs, skipped_frames:skipped, elements:elements};
"""
