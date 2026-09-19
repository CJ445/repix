/** Shown wherever an action sends the image to the server, so the local/remote split is never a surprise. */
export default function ServerNote() {
  return (
    <p className="note">
      This step sends your image to the Repix server to run the model. It&rsquo;s deleted after you download the
      result or when it expires.
    </p>
  )
}
