async function test() {
  try {
    const response = await fetch('https://www.upwork.com/l', {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
      }
    });
    console.log('Status:', response.status);
    const text = await response.text();
    console.log('Text length:', text.length);
  } catch (err: any) {
    console.error('Error:', err.message);
  }
}
test();
