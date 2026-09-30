/**
 * `#/buttons`: every button variant, live and held (item 182, commit 4) - the
 * Storybook-equivalent reference, inside the product so it draws with the
 * product's own stylesheet, theme and fonts rather than a copy of them. Linked
 * from `docs/design-language.md`. Nothing on it does anything but open its own
 * confirmations: every action here is a no-op.
 */
import { useState } from "react";
import { entry } from "./glossary";
import { DangerButton, LinkButton, PrimaryButton, SecondaryButton, SpendButton, VARIANTS } from "./buttons";
import { Card } from "./components";

export function ButtonsView() {
  const [pressed, setPressed] = useState<string | null>(null);
  const noop = (name: string) => () => setPressed(name);
  const live: Record<string, JSX.Element> = {
    primary: <PrimaryButton onClick={noop("primary")}>Start an audit</PrimaryButton>,
    secondary: <SecondaryButton onClick={noop("secondary")}>Copy the fix</SecondaryButton>,
    spend: <SpendButton price={0.4} onSpend={noop("spend")}
                        confirm={{ title: "Run the example analysis?",
                                   body: <p>A reference example. Confirming does nothing.</p>,
                                   action: "Run it" }}>Run analysis</SpendButton>,
    danger: <DangerButton onConfirm={noop("danger")}
                          confirm={{ title: "Remove the example?",
                                     body: <p>A reference example. Confirming does nothing.</p>,
                                     action: "Remove it" }}>Remove</DangerButton>,
    link: <LinkButton href="#/buttons">Open the catalogue</LinkButton>,
  };
  const held: Record<string, JSX.Element> = {
    primary: <PrimaryButton why="the audit list is still loading" onClick={noop("x")}>Start an audit</PrimaryButton>,
    secondary: <SecondaryButton why="nothing to copy yet" onClick={noop("x")}>Copy the fix</SecondaryButton>,
    spend: <SpendButton price={undefined} onSpend={noop("x")}
                        confirm={{ title: "", body: null, action: "" }}>Run analysis</SpendButton>,
    danger: <DangerButton why="another task is running" onConfirm={noop("x")}
                          confirm={{ title: "", body: null, action: "" }}>Remove</DangerButton>,
    link: <LinkButton href="#/buttons">Open the catalogue</LinkButton>,
  };
  return (
    <div className="btn-ref">
      <h2>Buttons</h2>
      <p className="muted">
        The five variants every screen draws its controls from (item 182). A variant is
        told by its tone and never by its size; held is any of them with its reason beside
        it. The pressed log below is the only thing a press here changes.
      </p>
      <Card>
        <div className="table-scroll">
        <table className="findings btn-ref-table">
          <thead><tr><th scope="col">Variant</th><th scope="col">Means</th>
                     <th scope="col">Live</th><th scope="col">Held</th></tr></thead>
          <tbody>
            {VARIANTS.map((v) => (
              <tr key={v.variant}>
                <th scope="row"><code>{v.component}</code><div className="muted">{v.variant} · <code>tone-{v.tone}</code></div></th>
                <td>{entry(v.registry).full}</td>
                <td data-variant={v.variant} data-held="false">{live[v.variant]}</td>
                <td data-variant={v.variant} data-held={v.variant === "link" ? "false" : "true"}>
                  {held[v.variant]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </Card>
      <p className="muted" role="status" aria-live="polite">{pressed ? `Pressed: ${pressed}` : ""}</p>
    </div>
  );
}
