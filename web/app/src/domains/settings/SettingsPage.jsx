import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {useEffect, useState} from 'react';
import {useSettingsStore} from '../../state/StudioProvider.jsx';

export function SettingsPage() {
  const {settings, saveSettings} = useSettingsStore();
  const preferences = settings.find((item) => item.category === 'operator_preferences' && item.key === 'studio_preferences')?.value || {};
  const environment = settings.find((item) => item.category === 'environment')?.value || {};
  const workspace = settings.find((item) => item.category === 'workspace')?.value || {};
  const [form, setForm] = useState({
    default_profile: '',
    default_concurrency: 10,
    default_real_generation: false
  });

  useEffect(() => {
    setForm({
      default_profile: preferences.default_profile || environment.default_profile || 'no_vlm_production',
      default_concurrency: preferences.default_concurrency || environment.default_concurrency || 10,
      default_real_generation: Boolean(preferences.default_real_generation)
    });
  }, [settings]);

  const onSubmit = async (event) => {
    event.preventDefault();
    await saveSettings(form);
  };

  return (
    <section className="grid-two">
      <div className="panel">
        <SectionTitle title="Operator Preferences" />
        <form className="stack compact" onSubmit={onSubmit}>
          <label><span>Default profile</span><input value={form.default_profile} onChange={(event) => setForm({...form, default_profile: event.target.value})} /></label>
          <label><span>Default concurrency</span><input type="number" value={form.default_concurrency} onChange={(event) => setForm({...form, default_concurrency: Number(event.target.value)})} /></label>
          <button type="button" className={`toggle ${form.default_real_generation ? 'active' : ''}`} onClick={() => setForm({...form, default_real_generation: !form.default_real_generation})}>Default real generation</button>
          <div className="action-row">
            <button type="submit">Save preferences</button>
          </div>
        </form>
      </div>
      <div className="panel">
        <SectionTitle title="Workspace / Environment" />
        <dl className="details">
          <div><dt>Workspace root</dt><dd>{workspace.workspace_root || 'n/a'}</dd></div>
          <div><dt>Runtime dir</dt><dd>{workspace.runtime_dir || 'n/a'}</dd></div>
          <div><dt>FastGen URL</dt><dd>{environment.fastgen_api_url || 'n/a'}</dd></div>
          <div><dt>FastGen model</dt><dd>{environment.fastgen_model || 'n/a'}</dd></div>
          <div><dt>FASTGEN key configured</dt><dd>{String(environment.fastgen_api_key_configured ?? false)}</dd></div>
        </dl>
      </div>
    </section>
  );
}
