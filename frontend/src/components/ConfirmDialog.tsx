import Modal from './Modal'

interface Props {
  title: string
  message: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}

/** Confirmation for an irreversible action. Cancel is the focused default. */
export default function ConfirmDialog({ title, message, confirmLabel, onConfirm, onCancel }: Props) {
  return (
    <Modal titleId="confirm-title" onClose={onCancel}>
      <h2 id="confirm-title" className="text-lg font-semibold">
        {title}
      </h2>
      <p className="mt-2 text-ink-2">{message}</p>
      <div className="mt-6 flex justify-end gap-2">
        <button data-autofocus onClick={onCancel} className="btn btn-secondary">
          Cancel
        </button>
        <button onClick={onConfirm} className="btn btn-primary">
          {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}
