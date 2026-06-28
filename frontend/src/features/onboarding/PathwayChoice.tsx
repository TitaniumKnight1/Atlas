import { Button } from "../../components";

interface PathwayChoiceProps {
  current: "setup" | "join";
}

export function PathwayChoice({ current }: PathwayChoiceProps) {
  return (
    <div className="pathway-choice atlas-panel">
      <p className="muted-text">Choose your onboarding path:</p>
      <div className="inline-actions">
        {current === "setup" ? (
          <Button variant="primary" disabled>
            New server setup
          </Button>
        ) : (
          <Button variant="secondary" onClick={() => (window.location.hash = "#/setup")}>
            New server setup
          </Button>
        )}
        {current === "join" ? (
          <Button variant="primary" disabled>
            Join a team
          </Button>
        ) : (
          <Button variant="secondary" onClick={() => (window.location.hash = "#/adopt")}>
            Join a team
          </Button>
        )}
      </div>
    </div>
  );
}
