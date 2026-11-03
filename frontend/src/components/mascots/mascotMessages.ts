/** Signature IMPACTMAP mascots: 24 developer messages each. */

export const RABBIT_MESSAGES = [
  "404: carrot not found!",
  "Why did the developer go broke? Because they used up all their cache!",
  "Keep hopping. Your code will get there!",
  "I run faster than your while loop!",
  "Have you tried turning it off and on again?",
  "There is no bug. It's an unexpected feature!",
  "sudo make me a carrot!",
  "Debugging is just being a detective in a crime movie where you are also the criminal.",
  "I asked the compiler for a joke. It didn't return anything.",
  "My code has zero bugs. It has undocumented features.",
  "git commit -m 'please work' is a valid strategy. Probably.",
  "Why do rabbits make great reviewers? We spot every hop in the logic.",
  "I would unit test my jumps, but gravity keeps mocking me.",
  "Your tests are green! My ears are pink. We're both thriving.",
  "A carrot a day keeps the null pointer away.",
  "I refactored my burrow. Same hole, cleaner architecture.",
  "REST? I prefer hoppin' around the endpoint.",
  "Stack Overflow is not a place to nap. I checked twice.",
  "You miss 100% of the commits you don't push.",
  "I'm not procrastinating. I'm waiting for my dependencies to resolve.",
  "Why was the function so relaxed? It had no side effects!",
  "Speed is fun, but shipping is funner!",
  "My favorite design pattern is 'it works on my machine'.",
  "Don't worry — every great project starts as a weird little script.",
];

export const TORTOISE_MESSAGES = [
  "Slow code is better than no code. But optimized code is better!",
  "Consistency beats speed. Every single commit.",
  "One bug at a time, little human.",
  "Why do programmers prefer dark mode? Because light attracts bugs.",
  "A good developer writes code. A great developer writes understandable code.",
  "Patience, young coder. Even compilation takes time.",
  "The best code is code you don't have to debug.",
  "Keep calm and commit often.",
  "A test today saves a scroll through logs tomorrow.",
  "I don't rush. I iterate.",
  "Shell? No, I carry my own architecture.",
  "Refactor slowly. Sleep soundly.",
  "Every long journey begins with a single stack trace.",
  "You can't regex your way out of every problem. Trust me.",
  "Naming things is hard. That's why we do it carefully.",
  "A clean diff is a love letter to your future self.",
  "The tortoise wins because the rabbit forgot to update the lockfile.",
  "Documentation is a gift. Wrap it with a bow.",
  "If it's flaky, it's not a test. It's a rumor.",
  "Measure twice, deploy once.",
  "Small commits are like small steps: easier to undo.",
  "Your code doesn't need to be perfect. It needs to be honest.",
  "Rest is part of the process. Even CPUs have idle states.",
  "The best time to add tests was yesterday. The second best is now.",
];

export function pickMessage(messages: string[], previous?: string | null): string {
  if (messages.length === 0) return "";
  if (messages.length === 1) return messages[0];
  let next = messages[Math.floor(Math.random() * messages.length)];
  let guard = 0;
  while (next === previous && guard < 8) {
    next = messages[Math.floor(Math.random() * messages.length)];
    guard += 1;
  }
  return next;
}
