import { Injectable, UnauthorizedException, ConflictException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';

@Injectable()
export class AuthService {
  constructor(
    private prisma: PrismaService,
    private jwt: JwtService,
  ) { }

  async register(email: string, name: string, surname: string, password: string, passwordConfirm: string) {
    const existing = await this.prisma.prisma.user.findUnique({
      where: { email },
    });

    if (existing) {
      throw new ConflictException('User already exists');
    }

    if (password !== passwordConfirm) {
      throw new ConflictException('Passwords do not match');
    }

    const hash = await bcrypt.hash(password, 10);

    const user = await this.prisma.prisma.user.create({
      data: {
        email,
        name,
        surname,
        passwordHash: hash,
      },
    });

    return this.generateToken(user.id, user.email);
  }

  async login(email: string, password: string) {
    const user = await this.prisma.prisma.user.findUnique({
      where: { email },
    });

    if (!user) throw new UnauthorizedException();

    const valid = await bcrypt.compare(password, user.passwordHash);

    if (!valid) throw new UnauthorizedException();

    return this.generateToken(user.id, user.email);
  }

  private generateToken(userId: string, email: string) {
    return {
      access_token: this.jwt.sign({
        sub: userId,
        email,
      }),
    };
  }
}
