import React from 'react';

interface SkeletonLoaderProps {
  type: 'text' | 'card' | 'message' | 'table-row';
  count?: number;
}

export const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({ type, count = 1 }) => {
  const items = Array.from({ length: count }, (_, i) => i);

  if (type === 'card') {
    return (
      <>
        {items.map(i => (
          <div key={i} className="category-card" style={{ cursor: 'default' }}>
            <div className="skeleton" style={{ width: '56px', height: '56px', borderRadius: 'var(--radius-md)', marginBottom: '1.25rem' }} />
            <div className="skeleton skeleton-text" style={{ width: '60%', height: '1.25rem' }} />
            <div className="skeleton skeleton-text" style={{ width: '100%' }} />
            <div className="skeleton skeleton-text" style={{ width: '80%' }} />
          </div>
        ))}
      </>
    );
  }

  if (type === 'message') {
    return (
      <>
        {items.map(i => (
          <div key={i} className="message-wrapper" style={{ animation: 'none' }}>
            <div className="skeleton avatar bot" style={{ border: 'none' }} />
            <div className="message-content">
              <div className="message-bubble" style={{ background: 'transparent', padding: '0.5rem 0', boxShadow: 'none', border: 'none' }}>
                <div className="skeleton skeleton-text" style={{ width: '90%' }} />
                <div className="skeleton skeleton-text" style={{ width: '100%' }} />
                <div className="skeleton skeleton-text" style={{ width: '75%' }} />
              </div>
            </div>
          </div>
        ))}
      </>
    );
  }

  if (type === 'table-row') {
    return (
      <>
        {items.map(i => (
          <tr key={i}>
            <td><div className="skeleton skeleton-text" style={{ margin: 0 }} /></td>
            <td><div className="skeleton skeleton-text" style={{ width: '50%', margin: 0 }} /></td>
            <td><div className="skeleton" style={{ width: '60px', height: '24px', borderRadius: '4px' }} /></td>
            <td className="text-right"><div className="skeleton" style={{ width: '100px', height: '32px', borderRadius: '4px', marginLeft: 'auto' }} /></td>
          </tr>
        ))}
      </>
    );
  }

  // Default text
  return (
    <div style={{ width: '100%' }}>
      {items.map(i => (
        <div key={i} className="skeleton skeleton-text" />
      ))}
    </div>
  );
};
