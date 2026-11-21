// Numbers in headlines: words up to twenty, as a sentence reads them,
// figures above that.

const WORDS = [
  "no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
  "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
  "eighteen", "nineteen", "twenty",
];

export const inWords = (n: number) => WORDS[n] ?? String(n);

// The same, starting a sentence.
export const InWords = (n: number) => {
  const word = inWords(n);
  return word.charAt(0).toUpperCase() + word.slice(1);
};
