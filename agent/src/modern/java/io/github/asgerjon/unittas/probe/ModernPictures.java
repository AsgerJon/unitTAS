package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.NativeImage;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;

import java.io.File;
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

/**
 * Pictures in 26.3 (PROTOCOL.md 8.11; SPEC.md 19.7 step 2), as 1.7.10's: the chat cleared, the frame given its ticks
 * to show it, then the picture by the game's own screenshot of its main render target, written as a PNG. 26.3's renderer
 * hands the picture back a frame or two after it is asked for, so it is waited for by ticks.
 */
final class ModernPictures {

	/** The client ticks the picture may take to come back. */
	private static final int PICTURE_TICKS = 40;

	private ModernPictures() {
	}

	static void bind(Probe probe) {
		probe.op("screenshot").does(ModernPictures::before).settles(ModernPictures::take);
	}

	private static JsonElement before(Call call) throws ProbeException {
		String file = call.string("file", null);
		if (file == null || !new File(file).isAbsolute()) {
			throw ProbeException.badRequest("file", "screenshot needs the file to write, an absolute path");
		}
		if (call.flag("clear_chat", true)) {
			Version.chat().clearMessages(false);
		}
		return new JsonObject();
	}

	/** After the chat is cleared, the ticks for the frame to show it all, then the picture, written on the client thread. */
	private static JsonElement take(Call call, JsonElement value) throws ProbeException, InterruptedException {
		ModernThings.waitClient(call, call.number("settle_ticks", 2, 0, 1200), value);
		File file = new File(call.string("file", null));
		CompletableFuture<int[]> written = new CompletableFuture<>();
		Sides.get().post(Side.CLIENT, () -> {
			Version.screenshot((NativeImage image) -> {
				try (image) {
					File folder = file.getParentFile();
					if (folder != null) {
						folder.mkdirs();
					}
					image.writeToFile(file);
					written.complete(new int[] {image.getWidth(), image.getHeight()});
				} catch (IOException | RuntimeException e) {
					written.completeExceptionally(e);
				}
			});
			return null;
		});
		for (int tick = 0; tick < PICTURE_TICKS && !written.isDone(); tick++) {
			ModernThings.waitClient(call, 1, value);
		}
		if (!written.isDone()) {
			throw new ProbeException("ProbeError", "the picture didn't come back in " + PICTURE_TICKS + " client ticks", null);
		}
		try {
			int[] size = written.join();
			return Json.object("file", file.getAbsolutePath(), "width", size[0], "height", size[1]);
		} catch (CompletionException e) {
			throw new ProbeException("ProbeError", "the picture couldn't be written: " + e.getCause(), null);
		}
	}
}
