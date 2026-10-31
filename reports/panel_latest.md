# Panel snapshot 2026-10-31

Probability of each question as worded, by source. Blank = no value (see notes).

| id | question | polymarket | metaculus | swift_centre | gjopen | my_prob | claude_prob |
|---|---|---:|---:|---:|---:|---:|---:|
| q1 | US-Iran ceasefire still in effect on 31 December 2026? | 0.275 |  |  |  |  | 0.300 |
| q2 | Official Russia-Ukraine ceasefire agreed by 31 December 2026? | 0.145 |  |  |  |  | 0.120 |
| q3 | Official Russia-Ukraine ceasefire agreed by 30 June 2027? | 0.525 |  |  |  |  | 0.450 |
| q4 | Sudan ceasefire agreed by 31 December 2026? | 0.100 |  |  |  |  | 0.080 |
| q5 | US or Israeli strikes on Iranian territory resume by 31 March 2027? | 0.610 |  |  | 0.417 |  | 0.700 |

## Notes

- **q1 / polymarket** (2026-10-31): wording: Resolves Yes unless the United States carries out a qualifying air or missile strike that impacts Iranian territory by 31 Dec 2026, 11:59 PM Iran time. Match is good but narrower than the wording: "ceasefire continues" means only "no US strike on Iran"; Iranian action against US forces, or a formal collapse without a strike, would not resolve it No.
- **q1 / metaculus** (2026-10-31): post_id not yet matched: the Metaculus API refused anonymous search; set METACULUS_TOKEN or fill post_id by hand; METACULUS_TOKEN not set; the Metaculus API refuses anonymous calls (HTTP 403)
- **q1 / swift_centre** (2026-10-31): no Swift Centre forecast on a US-Iran ceasefire holding; their nearest, 'US and Iran agree to a permanent peace deal by 31st May 2026' (6.5% on 27 Apr 2026), is a different question and has expired
- **q1 / gjopen** (2026-10-31): no GJ Open question on a US-Iran ceasefire; GJO 5630 (US deploys armed forces to mainland Iran before 19 Dec 2026) is about ground deployment, not strikes, so it was not used
- **q1 / my_prob** (2026-10-31): my_prob_q1 blank in every forward_log.csv row up to 2026-10-31
- **q1 / claude_prob** (2026-10-28): carried forward from the 2026-10-28 weekly entry
- **q2 / polymarket** (2026-10-31): wording: Resolves Yes if a mutually agreed, general suspension of direct military engagement is officially announced by both countries (or confirmed by a consensus of credible reporting) by 31 Dec 2026, 11:59 PM ET, whether or not it has taken effect. Matches the wording. The sibling market "Russia x Ukraine ceasefire by December 31, 2026" instead requires the ceasefire to take effect and hold for 10 days, so it was not used.
- **q2 / metaculus** (2026-10-31): post_id not yet matched: the Metaculus API refused anonymous search; set METACULUS_TOKEN or fill post_id by hand; METACULUS_TOKEN not set; the Metaculus API refuses anonymous calls (HTTP 403)
- **q2 / swift_centre** (2026-10-31): fetch failed: 403 Client Error: Forbidden for url: https://swiftcentre.substack.com/api/v1/posts/polymarket-vs-swift-centre-round
- **q2 / gjopen** (2026-10-31): no GJ Open question on a Russia-Ukraine ceasefire as of 2026-10-28
- **q2 / my_prob** (2026-10-31): my_prob_q2 blank in every forward_log.csv row up to 2026-10-31
- **q2 / claude_prob** (2026-10-28): carried forward from the 2026-10-28 weekly entry
- **q3 / polymarket** (2026-10-31): wording: Same resolution rules as q2 with a 30 Jun 2027 deadline. Matches the wording.
- **q3 / metaculus** (2026-10-31): post_id not yet matched: the Metaculus API refused anonymous search; set METACULUS_TOKEN or fill post_id by hand; METACULUS_TOKEN not set; the Metaculus API refuses anonymous calls (HTTP 403)
- **q3 / swift_centre** (2026-10-31): Swift Centre has only the 2026 ceasefire forecast (see q2), no 2027 horizon
- **q3 / gjopen** (2026-10-31): no GJ Open question on a Russia-Ukraine ceasefire as of 2026-10-28
- **q3 / my_prob** (2026-10-31): my_prob_q3 blank in every forward_log.csv row up to 2026-10-31
- **q3 / claude_prob** (2026-10-28): carried forward from the 2026-10-28 weekly entry
- **q4 / polymarket** (2026-10-31): wording: Resolves Yes on an official, publicly announced and mutually agreed halt in military engagement between the Sudanese Armed Forces and the Rapid Support Forces by 31 Dec 2026, 11:59 PM ET; humanitarian pauses and informal agreements do not count. Matches the wording, with the ceasefire defined as SAF-RSF specifically.
- **q4 / metaculus** (2026-10-31): post_id not yet matched: the Metaculus API refused anonymous search; set METACULUS_TOKEN or fill post_id by hand; METACULUS_TOKEN not set; the Metaculus API refuses anonymous calls (HTTP 403)
- **q4 / swift_centre** (2026-10-31): no Swift Centre forecast on Sudan
- **q4 / gjopen** (2026-10-31): no GJ Open question on Sudan as of 2026-10-28
- **q4 / my_prob** (2026-10-31): my_prob_q4 blank in every forward_log.csv row up to 2026-10-31
- **q4 / claude_prob** (2026-10-28): carried forward from the 2026-10-28 weekly entry
- **q5 / polymarket** (2026-10-31): logged as 1 - P(Yes) of the market (invert: true); wording: NO LIVE MARKET MATCHES THIS QUESTION. The "US/Israel strikes Iran by ..." event is closed (its 31 Dec 2026 market already resolved Yes, strikes having occurred earlier in 2026), and no market exists for strikes resuming by 31 Mar 2027. Closest live market: "Israel x Iran ceasefire continues through December 31?", logged inverted (1 - P(Yes)) as the probability that strikes resume. Differences: (1) covers Israel-Iran only; US strikes are covered separately by q1's market; (2) it resolves No on a qualifying strike by EITHER side, so an Iranian strike on Israel also counts as "resumed"; (3) the deadline is 31 Dec 2026, not 31 Mar 2027. Replace when a 2027 market appears.
- **q5 / metaculus** (2026-10-31): post_id not yet matched: the Metaculus API refused anonymous search; set METACULUS_TOKEN or fill post_id by hand; METACULUS_TOKEN not set; the Metaculus API refuses anonymous calls (HTTP 403)
- **q5 / swift_centre** (2026-10-31): Swift Centre's 'US military strike on Iran by March 31, 2026' (68%) resolved Yes in February 2026 and does not cover a resumption
- **q5 / gjopen** (2026-10-31): GJO 5487 'When will the IDF next attempt a military strike within Iran?': P(before 11 Dec 2026) = sum of the dated buckets. Differences: Israel only (no US strikes); 'attempt' rather than impact; deadline 10 Dec 2026, not 31 Mar 2027, so it is a lower bound on our question; sum of Before 24 July 2026 (0.001) + Between 24 July 2026 and 17 September 2026 (0.002) + Between 18 September 2026 and 10 December 2026 (0.414)
- **q5 / my_prob** (2026-10-31): my_prob_q5 blank in every forward_log.csv row up to 2026-10-31
- **q5 / claude_prob** (2026-10-28): carried forward from the 2026-10-28 weekly entry
