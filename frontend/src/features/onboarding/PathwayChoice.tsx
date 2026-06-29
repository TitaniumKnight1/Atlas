import { Button } from "../../components";

interface PathwayChoiceProps {
  current: "setup" | "join";
}

export function PathwayChoice({ current }: PathwayChoiceProps) {
  return (
    <div className="pathway-choice">
      <p className="pathway-choice__label">Choose your onboarding path:</p>
      <div className="pathway-choice__actions">
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
