import { Copy } from 'lucide-react';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { useToast } from '../Toast';

interface ShareResultButtonProps {
  /** Summary to share; the button is not rendered while there is no result. */
  text: string | null;
  /** The footer link class of the page this sits in, so it matches its neighbours. */
  className: string;
}

/** Shares through the system sheet on phones, and copies to the clipboard everywhere else. */
export function ShareResultButton({ text, className }: ShareResultButtonProps) {
  const toast = useToast();
  const isMobile = useMediaQuery('(max-width: 900px)');
  if (!text) return null;

  const handleClick = async () => {
    if (isMobile && typeof navigator.share === 'function') {
      try {
        await navigator.share({ text });
      } catch {
        // The student closed the share sheet: nothing to report.
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      toast.show('Đã sao chép kết quả', 'success');
    } catch {
      toast.show('Không sao chép được. Hãy thử lại.', 'error');
    }
  };

  return (
    <button type="button" className={`${className} tool-share-btn`} onClick={() => void handleClick()}>
      <Copy size={14} aria-hidden="true" />
      Sao chép kết quả
    </button>
  );
}
