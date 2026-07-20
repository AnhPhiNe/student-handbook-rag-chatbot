import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  private handleReload = () => {
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          backgroundColor: 'var(--bg-primary)',
          color: 'var(--text-primary)',
          padding: '2rem',
          textAlign: 'center'
        }}>
          <AlertTriangle size={64} color="var(--danger)" style={{ marginBottom: '1.5rem' }} />
          <h1 style={{ fontSize: '1.5rem', marginBottom: '1rem', fontWeight: 700 }}>Đã có lỗi không mong muốn xảy ra</h1>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem', maxWidth: '400px' }}>
            Chúng tôi xin lỗi vì sự bất tiện này. Đã có lỗi xảy ra trong quá trình hiển thị ứng dụng.
          </p>
          <button 
            onClick={this.handleReload}
            className="btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <RefreshCcw size={18} />
            Tải lại trang
          </button>
          
          {import.meta.env.DEV && this.state.error && (
            <div style={{ marginTop: '3rem', textAlign: 'left', maxWidth: '800px', width: '100%', background: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--danger)', overflow: 'auto' }}>
              <h3 style={{ color: 'var(--danger)', marginBottom: '0.5rem' }}>Chi tiết lỗi (Chỉ hiển thị ở chế độ DEV):</h3>
              <pre style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                {this.state.error.toString()}
                {'\n'}
                {this.state.error.stack}
              </pre>
            </div>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
