import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {PageHeader} from '../../shared/ui/PageHeader.jsx';
import {useEffect, useState} from 'react';
import {useSettingsStore} from '../../state/StudioProvider.jsx';

export function SettingsPage() {
  const {settings, saveSettings} = useSettingsStore();
  const preferences = settings.find((item) => item.category === 'operator_preferences' && item.key === 'studio_preferences')?.value || {};
  const environment = settings.find((item) => item.category === 'environment')?.value || {};
  const fastgen = settings.find((item) => item.category === 'provider_metadata' && item.provider === 'fastgen')?.value || {};
  const llmAuthoring = settings.find((item) => item.category === 'provider_metadata' && item.key === 'llm_authoring')?.value || {};
  const workspace = settings.find((item) => item.category === 'workspace')?.value || {};
  const auth = settings.find((item) => item.category === 'auth' && item.key === 'local_operator')?.value || {};
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
    <section className="stack wide-gap">
      <PageHeader
        eyebrow="Settings"
        title="Local studio settings"
        description="Store non-secret preferences, inspect provider metadata, and verify local workspace configuration."
        meta="local-first"
      />
      <div className="settings-grid">
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
          <div><dt>Default profile</dt><dd>{environment.default_profile || 'n/a'}</dd></div>
          <div><dt>Provider</dt><dd>FastGen</dd></div>
          <div><dt>FastGen URL</dt><dd>{fastgen.api_url || 'n/a'}</dd></div>
          <div><dt>FastGen model</dt><dd>{fastgen.model || 'n/a'}</dd></div>
          <div><dt>FASTGEN_API_KEY</dt><dd>{fastgen.api_key_configured ? 'Configured in environment' : 'Missing'}</dd></div>
          <div><dt>LLM authoring mode</dt><dd>{llmAuthoring.mode || 'disabled'}</dd></div>
          <div><dt>LLM authoring model</dt><dd>{llmAuthoring.model || 'n/a'}</dd></div>
          <div><dt>LLM authoring key</dt><dd>{llmAuthoring.api_key_configured ? 'Configured in environment' : 'Missing'}</dd></div>
          <div><dt>Secret storage</dt><dd>{fastgen.secret_storage || 'environment'}</dd></div>
          <div><dt>Operator account</dt><dd>{auth.username || 'operator'} / {auth.role || 'Admin'}</dd></div>
          <div><dt>Session TTL</dt><dd>{auth.session_ttl_hours || 12} hours</dd></div>
          <div><dt>Default credentials</dt><dd>{auth.default_credentials_active ? 'Active locally' : 'Changed'}</dd></div>
        </dl>
      </div>
      </div>
    </section>
  );
}
