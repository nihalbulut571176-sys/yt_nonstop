import {useEffect, useMemo, useState} from 'react';
import {Badge} from '../../shared/ui/Badge.jsx';
import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {reviewDecisionOptions} from '../../shared/types/contracts.js';
import {useReviewStore} from '../../state/StudioProvider.jsx';

export function ReviewPage() {
  const {reviewQueue, saveReviewDecision} = useReviewStore();
  const [selectedRowId, setSelectedRowId] = useState('');
  const [decision, setDecision] = useState('pending');
  const [note, setNote] = useState('');

  const items = reviewQueue?.items || [];

  const decisionLookup = useMemo(() => {
    const map = new Map();
    (reviewQueue?.decisions || []).forEach((item) => map.set(item.item_id, item));
    return map;
  }, [reviewQueue]);

  useEffect(() => {
    if (!selectedRowId && items[0]) {
      setSelectedRowId(items[0].item_id);
    }
  }, [items, selectedRowId]);

  useEffect(() => {
    if (!selectedRowId) return;
    const current = decisionLookup.get(selectedRowId);
    if (current) {
      setDecision(current.decision);
      setNote(current.note || '');
    } else {
      setDecision('pending');
      setNote('');
    }
  }, [selectedRowId, decisionLookup]);

  const selectedItem = items.find((item) => item.item_id === selectedRowId);

  const onSave = async () => {
    if (!selectedRowId) return;
    await saveReviewDecision({
      item_id: selectedRowId,
      source: selectedItem?.source || reviewQueue?.source || 'review',
      decision,
      note,
      payload: selectedItem?.payload || {}
    });
  };

  if (!reviewQueue) {
    return <section className="panel"><p className="muted">Select a project to inspect the review queue.</p></section>;
  }

  return (
    <section className="stack">
      <div className="panel">
        <SectionTitle title="Review Queue" meta={`${items.length} items`} />
        <div className="meta-row">
          <Badge tone="neutral">{reviewQueue.source || 'no source'}</Badge>
          <Badge tone="warn">manual review {reviewQueue.summary.manual_review || 0}</Badge>
          <Badge tone="accent">regenerate {reviewQueue.summary.regenerate || 0}</Badge>
          <Badge tone="success">decisions {reviewQueue.decisions.length}</Badge>
        </div>
      </div>
      <div className="grid-two">
        <div className="panel">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Status</th>
                  <th>Warning</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.item_id} className={selectedRowId === item.item_id ? 'row-selected' : ''} onClick={() => setSelectedRowId(item.item_id)}>
                    <td className="cell-highlight">{item.label}</td>
                    <td>{item.status || 'n/a'}</td>
                    <td>{item.warning || 'n/a'}</td>
                    <td>{item.action || 'n/a'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <SectionTitle title="Persisted Decision" meta={selectedRowId || 'Select an item'} />
          <div className="stack compact">
            <label>
              <span>Decision</span>
              <select value={decision} onChange={(event) => setDecision(event.target.value)}>
                {reviewDecisionOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label>
              <span>Note</span>
              <textarea rows={6} value={note} onChange={(event) => setNote(event.target.value)} />
            </label>
            <button onClick={onSave} disabled={!selectedRowId}>Save decision</button>
            {selectedItem ? <pre className="mono-box">{JSON.stringify(selectedItem.payload, null, 2)}</pre> : null}
          </div>
        </div>
      </div>
    </section>
  );
}
