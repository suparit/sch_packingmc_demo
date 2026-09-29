
# 3D assets

The active pages use `export/Machine.glb`. `Run.glb` and `Tast.glb` are valid GLB v2 files retained as alternate project assets.

The former `Keep.glb` was a 1-byte Git blob (2 bytes in the Windows checkout), had no GLB header, had no reference in HTML/JavaScript, and had no valid revision in repository history. It was removed instead of being replaced with guessed geometry. If a distinct model named **Keep** is required later, obtain the original authored/exported GLB and validate its provenance before adding it.

`index1.html` continues running its controls, WebSocket client, renderer, and event log if the active model fails to load; the loader reports the GLB error in the event log. Do not substitute another machine model under a misleading filename.
