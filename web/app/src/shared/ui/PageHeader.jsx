import {Badge} from './Badge.jsx';

export function PageHeader({eyebrow, title, description, actions, meta}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      <div className="page-header-side">
        {meta ? <Badge tone="neutral">{meta}</Badge> : null}
        {actions}
      </div>
    </header>
  );
}
