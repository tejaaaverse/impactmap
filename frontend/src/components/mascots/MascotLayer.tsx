import { Mascot } from "./Mascot";
import { RABBIT_MESSAGES, TORTOISE_MESSAGES } from "./mascotMessages";

/**
 * Mounts both signature companions once, globally. They roam independently of
 * routing so the universe follows the user through every page.
 */
export function MascotLayer() {
  return (
    <div data-mascot-layer className="pointer-events-none fixed inset-0 z-30">
      <Mascot
        kind="rabbit"
        src="/assets/rabbit-pixel.svg"
        alt="Lavender pixel-art rabbit mascot"
        name="Pip the Rabbit"
        messages={RABBIT_MESSAGES}
        size={66}
        anchor="bottom-right"
      />
      <Mascot
        kind="tortoise"
        src="/assets/tortoise-pixel.svg"
        alt="Purple pixel-art tortoise mascot"
        name="Moss the Tortoise"
        messages={TORTOISE_MESSAGES}
        size={72}
        anchor="bottom-left"
      />
    </div>
  );
}
