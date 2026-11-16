package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.resources.sounds.SimpleSoundInstance;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.resources.Identifier;
import net.minecraft.sounds.SoundEvent;

import java.util.Arrays;

/**
 * Sounds in 26.3 (PROTOCOL.md 8.10 and 7; SPEC.md 19.7 step 2), as 1.7.10's: every sound the client is asked to play
 * is a sound event when asked for, by its id, whether the game has it (one it hasn't plays nothing without a word, so
 * its event names who asked for it), its volume, pitch and place; sound.play plays one, as a button's click does.
 */
public final class FabricSounds {

	private FabricSounds() {
	}

	static void bind(Probe probe) {
		probe.op("sound.play").does(FabricSounds::play);
	}

	private static JsonElement play(Call call) throws ProbeException {
		String id = call.string("id", null);
		Identifier key = id == null ? null : Identifier.tryParse(id);
		if (key == null) {
			throw ProbeException.badRequest("id", "sound.play needs the sound's id");
		}
		float pitch = call.has("pitch") ? call.args.get("pitch").getAsFloat() : 1.0F;
		Minecraft.getInstance().getSoundManager().play(SimpleSoundInstance.forUI(SoundEvent.createVariableRangeEvent(key),
			pitch));
		return new JsonObject();
	}

	/**
	 * A sound the client is asked to play (SoundManager.play, through MixinSoundManager), before the engine plays it:
	 * resolved here (getOrResolve, which the engine then reuses), so its volume reads whether or not the game has it.
	 */
	public static void heard(SoundManager manager, SoundInstance sound) {
		Probe probe = Probe.get();
		if (probe == null || sound == null || !probe.events.sound) {
			return;
		}
		Identifier id = sound.getIdentifier();
		if (id.getPath().isEmpty() || id.getPath().equals("intentionally_empty")) {
			// no sound, on purpose
			return;
		}
		boolean known = sound.getOrResolve(manager) != null;
		probe.event("sound", Json.object("id", id.toString(), "known", known, "from", known ? null : caller(),
			"volume", (double) sound.getVolume(), "pitch", (double) sound.getPitch(),
			"pos", Arrays.asList(sound.getX(), sound.getY(), sound.getZ())));
	}

	/** The first few calls outside the sound system, the mixin and this class, to say who asked for a sound. */
	private static String caller() {
		StringBuilder calls = new StringBuilder();
		int shown = 0;
		for (StackTraceElement frame : Thread.currentThread().getStackTrace()) {
			String owner = frame.getClassName();
			if (owner.startsWith("java.") || owner.startsWith("net.minecraft.client.sounds.")
				|| owner.contains("MixinSoundManager") || owner.equals(FabricSounds.class.getName())) {
				continue;
			}
			calls.append(shown == 0 ? "" : " < ").append(owner.substring(owner.lastIndexOf('.') + 1)).append('.')
				.append(frame.getMethodName()).append(':').append(frame.getLineNumber());
			if (++shown == 5) {
				break;
			}
		}
		return calls.toString();
	}
}
