"""Sample Facebook Marketplace HTML fixtures for testing parser without live web requests."""

MARKETPLACE_RESULTS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Marketplace Search</title></head>
<body>
  <div role="main">
    <!-- Listing 1: Standard Damaged Honda Civic -->
    <a href="/marketplace/item/1029384756/?ref=search" class="x1i10hfl">
      <div>
        <img src="https://example.com/photos/civic1.jpg" alt="2012 Honda Civic LX - Damaged front bumper" />
      </div>
      <div>
        <span>$1,400</span>
      </div>
      <div>
        <span>2012 Honda Civic LX - Runs good but damaged front bumper</span>
      </div>
      <div>
        <span>Portland, OR</span>
      </div>
      <div>
        <span>145K miles</span>
      </div>
    </a>

    <!-- Listing 2: Non-running truck with blown engine -->
    <a href="/marketplace/item/5566778899/?ref=search" class="x1i10hfl">
      <div>
        <img src="https://example.com/photos/truck.jpg" alt="2005 Ford F-150" />
      </div>
      <div>
        <span>$800</span>
      </div>
      <div>
        <span>2005 Ford F-150 - Blown engine, non running, mechanic special</span>
      </div>
      <div>
        <span>Vancouver, WA</span>
      </div>
      <div>
        <span>180K miles</span>
      </div>
    </a>

    <!-- Listing 3: Excluded item (Parts only) -->
    <a href="/marketplace/item/9988776655/?ref=search" class="x1i10hfl">
      <div>
        <img src="https://example.com/photos/parts.jpg" alt="Civic parts" />
      </div>
      <div>
        <span>$200</span>
      </div>
      <div>
        <span>Honda Civic headlights and bumper - Parts only</span>
      </div>
      <div>
        <span>Portland, OR</span>
      </div>
    </a>
  </div>
</body>
</html>
"""

CHECKPOINT_HTML = """
<!DOCTYPE html>
<html>
<head><title>Security Checkpoint</title></head>
<body>
  <div>
    <h2>Confirm Your Identity</h2>
    <p>Please enter the code sent to your phone to approve your login.</p>
  </div>
</body>
</html>
"""

RESTRICTED_HTML = """
<!DOCTYPE html>
<html>
<head><title>Restricted</title></head>
<body>
  <div>
    <h2>You're temporarily blocked</h2>
    <p>Marketplace isn't available to you right now.</p>
  </div>
</body>
</html>
"""
