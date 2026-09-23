#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>
#import <QuartzCore/QuartzCore.h>

// ── Token Lifecycle Helper ─────────────────────────────────────────────────
// Reads ~/.ghost_copilot/session_token written by app.py daemon on startup.
// Falls back to COPILOT_AUTH_TOKEN env var (set in .env before launch).
// This keeps Objective-C requests authenticated after the H-1 security fix.
static NSString *GhostLoadSessionToken(void) {
    // 1. Env var override
    const char *envVal = getenv("COPILOT_AUTH_TOKEN");
    if (envVal && strlen(envVal) > 0) {
        return [NSString stringWithUTF8String:envVal];
    }
    // 2. Token file written by daemon
    NSString *home = NSHomeDirectory();
    NSString *tokenPath = [home stringByAppendingPathComponent:@".ghost_copilot/session_token"];
    NSError *err = nil;
    NSString *token = [NSString stringWithContentsOfFile:tokenPath encoding:NSUTF8StringEncoding error:&err];
    if (!err && token.length > 0) {
        return [token stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    }
    return @""; // No token — daemon will reject; user should check setup
}
// ──────────────────────────────────────────────────────────────────────────

@interface GhostAppDelegate : NSObject <NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate>
@property (strong) NSWindow *window;
@property (strong) WKWebView *webView;
@property (assign) NSInteger retryCount;
@property (assign) BOOL isHidden;
@property (assign) BOOL isPTTActive;
@property (assign) BOOL isScreenVisible;
@property (strong) NSString *sessionToken;
@end

@implementation GhostAppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.retryCount = 0;
    self.isHidden = NO;
    self.isPTTActive = NO;
    self.isScreenVisible = NO;
    self.sessionToken = GhostLoadSessionToken();  // Load daemon auth token
    NSString *iconPath = [[[NSProcessInfo processInfo].arguments[0]
        stringByDeletingLastPathComponent]
        stringByAppendingPathComponent:@"ghost_copilot.icns"];
    if (![[NSFileManager defaultManager] fileExistsAtPath:iconPath]) {
        iconPath = [[[[NSProcessInfo processInfo].arguments[0]
            stringByDeletingLastPathComponent]
            stringByDeletingLastPathComponent]
            stringByAppendingPathComponent:@"Resources/AppIcon.icns"];
    }
    NSImage *icon = [[NSImage alloc] initWithContentsOfFile:iconPath];
    if (icon) [NSApp setApplicationIconImage:icon];

    NSScreen *screen = [NSScreen mainScreen];
    NSRect sr = screen ? [screen visibleFrame] : NSMakeRect(0, 0, 1440, 900);
    CGFloat w = 460, h = 800;
    NSRect rect = NSMakeRect(NSMaxX(sr) - w - 16, NSMaxY(sr) - h - 16, w, h);

    self.window = [[NSWindow alloc] initWithContentRect:rect
        styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                   NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable |
                   NSWindowStyleMaskFullSizeContentView)
        backing:NSBackingStoreBuffered defer:NO];

    [self.window setSharingType:NSWindowSharingNone]; // Start: ghost (invisible to screen share)
    [self.window setLevel:NSFloatingWindowLevel];
    [self.window setCollectionBehavior:(NSWindowCollectionBehaviorCanJoinAllSpaces |
                                        NSWindowCollectionBehaviorFullScreenAuxiliary)];
    [self.window setTitlebarAppearsTransparent:YES];
    [self.window setTitleVisibility:NSWindowTitleHidden];
    [self.window setMovableByWindowBackground:YES];
    [self.window setBackgroundColor:[NSColor colorWithRed:0.04 green:0.04 blue:0.06 alpha:0.98]];
    [self.window setHasShadow:YES];
    [self.window setTitle:@"Interview Assistant"];

    WKWebViewConfiguration *config = [[WKWebViewConfiguration alloc] init];
    config.preferences.javaScriptCanOpenWindowsAutomatically = NO;
    [config.preferences setValue:@NO forKey:@"allowFileAccessFromFileURLs"];

    self.webView = [[WKWebView alloc] initWithFrame:self.window.contentView.bounds configuration:config];
    self.webView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    self.webView.UIDelegate = self;
    self.webView.navigationDelegate = self;
    [self.webView setValue:@NO forKey:@"drawsBackground"];
    [self.window.contentView addSubview:self.webView];

    self.window.alphaValue = 0.0;
    [self.window makeKeyAndOrderFront:nil];
    [NSAnimationContext runAnimationGroup:^(NSAnimationContext *ctx) {
        ctx.duration = 0.2;
        ctx.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseOut];
        [self.window.animator setAlphaValue:1.0];
    }];

    [self.window makeFirstResponder:self.webView];

    // GLOBAL key monitor — works even when Zoom/Meet has focus
    // Use Option+Space (keyCode 49 with Option), Ctrl+Space (keyCode 49 with Control), or F5 (keyCode 96)
    // Never intercept bare Spacebar globally so typing across other apps is preserved!
    [NSEvent addGlobalMonitorForEventsMatchingMask:NSEventMaskKeyDown handler:^(NSEvent *event) {
        BOOL isOptOrCtrlSpace = (event.keyCode == 49 && ((event.modifierFlags & NSEventModifierFlagOption) || (event.modifierFlags & NSEventModifierFlagControl)));
        BOOL isF5 = (event.keyCode == 96);
        if ((isOptOrCtrlSpace || isF5) && !event.isARepeat) {
            [self handlePTT];
        }
        if (event.keyCode == 53 && (event.modifierFlags & NSEventModifierFlagOption)) { // Option+Esc = hide/show
            dispatch_async(dispatch_get_main_queue(), ^{ [self handleEsc]; });
        }
    }];

    // LOCAL key monitor — when copilot window is focused
    [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown handler:^NSEvent *(NSEvent *event) {
        if (event.keyCode == 53) { [self handleEsc]; return nil; }
        // Let WebKit handle Spacebar (PTT), F5, P (stay), S (skip) natively so typing in input box works!
        return event;
    }];

    // Poll /sharing_mode every 600ms to update screen capture visibility
    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_BACKGROUND, 0), ^{
        while (YES) {
            NSString *currentToken = self.sessionToken;
            if (currentToken.length == 0) {
                currentToken = GhostLoadSessionToken();
                if (currentToken.length > 0) {
                    dispatch_async(dispatch_get_main_queue(), ^{
                        self.sessionToken = currentToken;
                    });
                }
            }
            NSURL *url = [NSURL URLWithString:@"http://127.0.0.1:9471/sharing_mode"];
            NSMutableURLRequest *pollReq = [NSMutableURLRequest requestWithURL:url];
            if (currentToken.length > 0) {
                [pollReq setValue:[NSString stringWithFormat:@"Bearer %@", currentToken] forHTTPHeaderField:@"Authorization"];
            }
            dispatch_semaphore_t sem = dispatch_semaphore_create(0);
            __block NSData *data = nil;
            [[[NSURLSession sharedSession] dataTaskWithRequest:pollReq completionHandler:^(NSData *d, NSURLResponse *r, NSError *e) {
                data = d;
                dispatch_semaphore_signal(sem);
            }] resume];
            dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.0 * NSEC_PER_SEC)));
            if (data) {
                NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
                BOOL shouldBeVisible = [[json objectForKey:@"mode"] isEqualToString:@"visible"];
                dispatch_async(dispatch_get_main_queue(), ^{
                    if (shouldBeVisible != self.isScreenVisible) {
                        self.isScreenVisible = shouldBeVisible;
                        [self.window setSharingType:shouldBeVisible ? NSWindowSharingReadOnly : NSWindowSharingNone];
                    }
                });
            }
            [NSThread sleepForTimeInterval:0.6];
        }
    });

    [self loadHUD];
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)handleEsc {
    self.isHidden = !self.isHidden;
    if (self.isHidden) {
        [self.window setAlphaValue:0.0];
        [self.window setIgnoresMouseEvents:YES];
    } else {
        [self.window setAlphaValue:1.0];
        [self.window setIgnoresMouseEvents:NO];
        [self.window makeKeyAndOrderFront:nil];
        [self.window makeFirstResponder:self.webView];
    }
}

- (void)handlePTT {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.sessionToken.length == 0) {
            self.sessionToken = GhostLoadSessionToken();
        }
        NSURL *url = [NSURL URLWithString:@"http://127.0.0.1:9471/toggle_ptt"];
        NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:url];
        req.HTTPMethod = @"POST";
        // Attach session auth token so the daemon accepts this request (H-1 fix)
        if (self.sessionToken.length > 0) {
            [req setValue:[NSString stringWithFormat:@"Bearer %@", self.sessionToken] forHTTPHeaderField:@"Authorization"];
        }
        [[[NSURLSession sharedSession] dataTaskWithRequest:req completionHandler:^(NSData *d, NSURLResponse *r, NSError *e) {}] resume];
    });
}

- (void)loadHUD {
    if (self.sessionToken.length == 0) {
        self.sessionToken = GhostLoadSessionToken();
    }
    NSURL *url = [NSURL URLWithString:@"http://127.0.0.1:9471"];
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:url];
    if (self.sessionToken.length > 0) {
        [req setValue:[NSString stringWithFormat:@"Bearer %@", self.sessionToken] forHTTPHeaderField:@"Authorization"];
    }
    [self.webView loadRequest:req];
}

- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation {
    [self.window makeFirstResponder:self.webView];
    [self.webView evaluateJavaScript:@"window.focus(); if (document.body) document.body.focus();" completionHandler:nil];
}

// Faster retry: 100ms intervals, up to 60 tries = 6 seconds max wait
- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)nav withError:(NSError *)error {
    if (self.retryCount < 60) {
        self.retryCount++;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.1 * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
            if (self.sessionToken.length == 0) {
                self.sessionToken = GhostLoadSessionToken();
            }
            [self loadHUD];
        });
    }
}

// Strict navigation policy: Only allow communication with local daemon (127.0.0.1:9471)
- (void)webView:(WKWebView *)webView decidePolicyForNavigationAction:(WKNavigationAction *)navigationAction decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    NSURL *url = navigationAction.request.URL;
    NSString *scheme = [url.scheme lowercaseString];
    NSString *host = [url.host lowercaseString];
    NSInteger port = [url.port integerValue];

    if ([scheme isEqualToString:@"about"]) {
        decisionHandler(WKNavigationActionPolicyAllow);
        return;
    }

    if (([host isEqualToString:@"127.0.0.1"] || [host isEqualToString:@"localhost"]) && (port == 9471 || port == 0)) {
        decisionHandler(WKNavigationActionPolicyAllow);
        return;
    }

    // Proactively cancel any outbound URL navigation / external redirect attempts
    decisionHandler(WKNavigationActionPolicyCancel);
}

- (void)webView:(WKWebView *)webView requestMediaCapturePermissionForOrigin:(WKSecurityOrigin *)origin
initiatedByFrame:(WKFrameInfo *)frame type:(WKMediaCaptureType)type
decisionHandler:(void (^)(WKPermissionDecision))handler {
    handler(WKPermissionDecisionGrant);
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender { return YES; }

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        GhostAppDelegate *delegate = [[GhostAppDelegate alloc] init];
        [app setDelegate:delegate];
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        [app run];
    }
    return 0;
}
