import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button, Modal } from "@/components/ui";

/**
 * Warns before unsaved form changes are lost.
 *  - Clicking any in-app link (sidebar modules, buttons that are links) while the form is dirty opens a dialog:
 *    keep editing, discard and leave, or save and leave.
 *  - Closing or reloading the tab shows the browser's own "Leave site?" prompt.
 * `save` must return true when the save succeeded (leaving only continues then).
 * Not covered: the browser's Back button, which cannot be intercepted without a data router.
 */
export function useUnsavedChangesGuard(dirty: boolean, save: () => Promise<boolean>) {
  const navigate = useNavigate();
  const location = useLocation();
  const [pending, setPending] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const here = location.pathname + location.search;

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!dirtyRef.current || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!a || (a.target && a.target !== "_self") || a.hasAttribute("download")) return;
      const url = new URL(a.href, window.location.href);
      if (url.origin !== window.location.origin) return;
      const to = url.pathname + url.search + url.hash;
      if (url.pathname + url.search === here) return;
      e.preventDefault();
      e.stopPropagation();
      setPending(to);
    };
    const onUnload = (e: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    document.addEventListener("click", onClick, true);
    window.addEventListener("beforeunload", onUnload);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("beforeunload", onUnload);
    };
  }, [here]);

  const leave = () => { const to = pending; setPending(null); if (to) navigate(to); };
  const saveAndLeave = async () => {
    setSaving(true);
    try {
      if (await save()) leave();
      else setPending(null); // the form shows what is wrong; stay on the page
    } finally { setSaving(false); }
  };

  return (
    <Modal open={pending !== null} onClose={() => setPending(null)} title="You have unsaved changes"
      footer={<>
        <Button variant="secondary" onClick={() => setPending(null)} disabled={saving}>Keep editing</Button>
        <Button variant="danger" onClick={leave} disabled={saving}>Discard and leave</Button>
        <Button onClick={() => void saveAndLeave()} loading={saving}>Save and leave</Button>
      </>}>
      <p className="text-sm text-slate-600">The details you entered have not been saved. If you leave now they will be lost.</p>
    </Modal>
  );
}
