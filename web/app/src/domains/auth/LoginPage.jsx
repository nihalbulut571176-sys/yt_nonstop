import {useState} from 'react';
import {useStudioShell} from '../../state/StudioProvider.jsx';

export function LoginPage() {
  const {signIn, error} = useStudioShell();
  const [form, setForm] = useState({username: 'operator', password: 'operator'});

  const onSubmit = async (event) => {
    event.preventDefault();
    await signIn(form);
  };

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={onSubmit}>
        <p className="eyebrow">Production SaaS Shell</p>
        <h1>Sign in to yt_nonstop</h1>
        <p className="muted">The web studio wraps the local CLI pipeline and project workspace with durable app state, run history, and review workflows.</p>
        <label>
          <span>Username</span>
          <input value={form.username} onChange={(event) => setForm({...form, username: event.target.value})} />
        </label>
        <label>
          <span>Password</span>
          <input type="password" value={form.password} onChange={(event) => setForm({...form, password: event.target.value})} />
        </label>
        <button type="submit">Sign in</button>
        {error ? <p className="error-inline">{error}</p> : null}
      </form>
    </div>
  );
}
