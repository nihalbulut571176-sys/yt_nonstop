import {api} from '../../api.js';
import {Badge} from '../../shared/ui/Badge.jsx';
import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {PageHeader} from '../../shared/ui/PageHeader.jsx';
import {useProjectStore} from '../../state/StudioProvider.jsx';
import {useStudioShell} from '../../state/StudioProvider.jsx';

export function AssetsPage() {
  const {assets, preview, setPreview, selectedProjectId} = useProjectStore();
  const {setError} = useStudioShell();

  const openPreview = async (path) => {
    try {
      const payload = await api.preview(selectedProjectId, path);
      setPreview(payload);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  if (!assets) {
    return <section className="panel"><p className="muted">Select a project to inspect its assets.</p></section>;
  }

  const hasAssets = assets.groups.some((group) => group.entries.length > 0);

  return (
    <section className="stack wide-gap">
      <PageHeader
        eyebrow="Assets"
        title="Project artifact browser"
        description="Browse grouped project outputs while preserving local paths and controlled previews."
        meta={`${assets.total_count} assets`}
      />
      <div className="assets-workbench">
      <div className="panel">
        <SectionTitle title="Asset Collections" meta={`${assets.total_count} assets`} />
        {!hasAssets ? (
          <div className="empty-state">
            <strong>No indexed assets yet.</strong>
            <p>Run pipeline stages first, then this browser will group images, final delivery sets, videos, prompts, timelines, and reports.</p>
          </div>
        ) : null}
        <div className="stack">
          {assets.groups.map((group) => (
            <div key={group.type} className="asset-group">
              <div className="asset-group-head">
                <h3>{group.label}</h3>
                <Badge tone="neutral">{group.count}</Badge>
              </div>
              {group.entries.map((item) => (
                <button key={item.path} className="asset-row" onClick={() => openPreview(item.path)}>
                  <div>
                    <strong>{item.label}</strong>
                    <p>{item.path}</p>
                  </div>
                  <div className="meta-row">
                    <Badge tone="neutral">{item.preview_kind}</Badge>
                    <span>{Math.round(item.size / 1024)} KB</span>
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <SectionTitle title="Preview" meta={preview?.preview_kind || 'none'} />
        {!preview ? <p className="muted">Choose any asset to preview it.</p> : null}
        {preview?.preview_kind === 'image' ? <img className="asset-preview-image" src={api.mediaUrl(selectedProjectId, preview.path)} alt={preview.path} /> : null}
        {preview?.preview_kind === 'video' ? <video className="asset-preview-video" controls src={api.mediaUrl(selectedProjectId, preview.path)} /> : null}
        {preview?.preview_kind === 'text' ? <pre className="mono-box tall">{preview.content || 'No text preview available.'}</pre> : null}
        {preview?.preview_kind === 'binary' ? <p className="muted">{preview.path}</p> : null}
      </div>
      </div>
    </section>
  );
}
