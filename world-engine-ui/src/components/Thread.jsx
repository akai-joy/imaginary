// The signature element: a hairline lineage thread that marks whether a
// node/story branched from something earlier in the canon.
export default function Thread({ branched = false, tall = false }) {
  const h = tall ? 64 : 44
  return (
    <svg className="thread" width="22" height={h} viewBox={`0 0 22 ${h}`} aria-hidden="true">
      <path className="thread-line" d={`M11 0 V ${h}`} />
      <circle className="thread-node" cx="11" cy={h / 2} r="3.5" />
      {branched && <path className="thread-branch" d={`M11 ${h / 2} H 21`} />}
    </svg>
  )
}
